"""Offline queue-store conformance adapter; imports the requested Hermes checkout."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


_RUNTIME_ERRORS = (OSError, RuntimeError, ValueError, ImportError, LookupError, TypeError, AttributeError, sqlite3.Error)


class HermesQueue:
    def __init__(self, root, store_type, runtime):
        self.path = root / "state.db"
        self.store_type, self.runtime = store_type, runtime
        self.db = None
        self.open()

    def open(self):
        fresh = not self.path.exists()
        self.db = self.store_type(db_path=self.path)
        if fresh:
            for recipient in ("recipient-a", "recipient-b"):
                self.db.create_session(recipient, source="component-benchmark")
        self.epoch = self.runtime.begin_runtime_epoch(self.db, instance_id="offline-benchmark")
        self.recovered = self.runtime.recover_session_inputs(self.db, epoch=self.epoch)

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def reopen(self):
        self.close()
        self.open()

    def submit(self, text, token, recipient="recipient-a"):
        return self.runtime.admit_session_input(
            self.db, epoch=self.epoch, principal_id="benchmark-owner", session_id=recipient,
            request_id=token, payload={"text": text},
        )

    def claim(self, recipient="recipient-a"):
        return self.runtime.claim_session_input(self.db, epoch=self.epoch, session_id=recipient)

    def finish(self, row, outcome="completed", epoch=None):
        return self.runtime.settle_session_input(
            self.db, epoch=self.epoch if epoch is None else epoch,
            admission_id=row["admission_id"], generation=row["generation"], outcome=outcome,
        )

    def cancel(self, row):
        return self.runtime.cancel_session_input(self.db, epoch=self.epoch, admission_id=row["admission_id"])

    def get(self, row):
        return self.runtime.get_session_admission(self.db, admission_id=row["admission_id"])

    def rows(self, recipient="recipient-a", pending=True):
        return self.runtime.list_session_admissions(self.db, session_id=recipient, pending_only=pending)

    def execute_queued(self, recipient="recipient-a"):
        texts = []
        for _ in range(64):
            row = self.claim(recipient)
            if row is None:
                break
            texts.append(row["payload"]["text"])
            self.finish(row)
        return texts

    def refusal(self, operation):
        try:
            operation()
        except self.runtime.RuntimeStoreError as error:
            return error.reason
        return None


def queue_fifo(queue):
    expected = [f"work-{index}" for index in range(4)]
    for text in expected:
        queue.submit(text, text)
    executed = queue.execute_queued()
    return executed == expected, {"expected_order": expected, "executed_order": executed}


def queued_cancel_survives_reopen(queue):
    queue.submit("keep-first", "first")
    cancelled = queue.submit("cancel-me", "cancel")
    queue.submit("keep-last", "last")
    queue.cancel(cancelled)
    queue.reopen()
    saved = queue.get(cancelled)
    executed = queue.execute_queued()
    observed = {"cancelled_status": saved["status"], "cancelled_outcome": saved["outcome"], "executed": executed}
    return saved["outcome"] == "cancelled" and executed == ["keep-first", "keep-last"], observed


def active_cancel_refused(queue):
    queue.submit("running-work", "running")
    active = queue.claim()
    refused = queue.refusal(lambda: queue.cancel(active))
    after_cancel = queue.get(active)
    queue.finish(active, "interrupted")
    late_refusal = queue.refusal(lambda: queue.finish(active, "completed"))
    final = queue.get(active)
    observed = {
        "queued_cancel_refusal": refused, "status_after_refusal": after_cancel["status"],
        "late_completion_refusal": late_refusal, "final_status": final["status"], "final_outcome": final["outcome"],
        "boundary": "queue-store cancellation and terminal-state fencing; no provider interrupt",
    }
    return bool(refused) and after_cancel["status"] == "started" and final["outcome"] == "interrupted", observed


def restart_queued_retained(queue):
    admitted = [queue.submit(f"persist-{index}", f"persist-{index}") for index in range(3)]
    original_ids = [row["admission_id"] for row in admitted]
    queue.reopen()
    recovered_ids = [row["admission_id"] for row in queue.rows()]
    executed = queue.execute_queued()
    return original_ids == recovered_ids and executed == [f"persist-{index}" for index in range(3)], {
        "accepted_count": len(original_ids), "retained_count": len(recovered_ids),
        "identities_preserved": original_ids == recovered_ids, "executed": executed,
    }


def active_restart_honest(queue):
    queue.submit("uncertain-work", "uncertain")
    follower = queue.submit("follower", "follower")
    active = queue.claim()
    previous_epoch = queue.epoch
    queue.reopen()
    recovered = queue.get(active)
    blocked = queue.refusal(queue.claim)
    stale = queue.refusal(lambda: queue.finish(active, epoch=previous_epoch))
    follower_state = queue.get(follower)
    return recovered["status"] == "unknown" and bool(stale) and follower_state["status"] == "queued", {
        "recovered_status": recovered["status"], "recovered_outcome": recovered["outcome"],
        "follower_status": follower_state["status"], "next_claim_refusal": blocked,
        "old_owner_completion_refusal": stale, "recovery_entrypoint": "recover_session_inputs",
        "policy": "unknown execution pauses followers until explicit resolution",
    }


def recipient_separation(queue):
    queue.submit("for-a", "separate-a")
    other = queue.submit("for-b", "separate-b", "recipient-b")
    first = queue.execute_queued()
    other_before = queue.get(other)
    queue.reopen()
    second = queue.execute_queued("recipient-b")
    return first == ["for-a"] and other_before["status"] == "queued" and second == ["for-b"], {
        "recipient_a_executed": first, "recipient_b_before_reopen": other_before["status"],
        "recipient_b_executed": second,
    }


def duplicate_replay(queue):
    first = queue.submit("once", "stable-token")
    retry = queue.submit("once", "stable-token")
    executed = queue.execute_queued()
    queue.reopen()
    terminal_retry = queue.submit("once", "stable-token")
    one_identity = first["admission_id"] == retry["admission_id"] == terminal_retry["admission_id"]
    remaining = len(queue.rows())
    return one_identity and executed == ["once"] and remaining == 0, {
        "one_identity": one_identity, "executed": executed, "pending_after_terminal_retry": remaining,
        "terminal_replay_status": terminal_retry["status"], "terminal_replay_outcome": terminal_retry["outcome"],
    }


CASES = {
    "queue_fifo": (queue_fifo, "Accepted inputs execute once in admission order."),
    "queued_cancel_survives_reopen": (queued_cancel_survives_reopen, "Cancelled queued input remains cancelled after reopening."),
    "active_cancel_refused": (active_cancel_refused, "Queued cancellation refuses active work; interrupted terminal state rejects a late completion."),
    "restart_queued_retained": (restart_queued_retained, "Unstarted accepted inputs keep their identities and order across reopening."),
    "active_restart_honest": (active_restart_honest, "Uncertain started work is neither replayed nor falsely completed after restart."),
    "recipient_separation": (recipient_separation, "Draining one recipient leaves another recipient's work intact."),
    "duplicate_replay": (duplicate_replay, "The same idempotency token replays one accepted item before and after completion/reopen."),
}


def safe_error(error, source, state_root):
    message = str(error).replace(str(source), "<source>").replace(str(state_root), "<state>")
    message = message.replace(str(Path.home()), "<home>")
    return {"type": type(error).__name__, "message": message[:500]}


def measure_case(case_id, operation, expected, root, source, store_type, runtime):
    started = time.perf_counter()
    queue = None
    try:
        queue = HermesQueue(root, store_type, runtime)
        passed, observed = operation(queue)
        return {"id": case_id, "status": "pass" if passed else "fail", "expected": expected,
                "observed": observed, "duration_ms": round((time.perf_counter() - started) * 1000, 3)}
    except _RUNTIME_ERRORS as error:
        return {"id": case_id, "status": "runtime_error", "expected": expected,
                "observed": safe_error(error, source, root), "duration_ms": round((time.perf_counter() - started) * 1000, 3)}
    finally:
        if queue is not None:
            queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    source = parser.parse_args().source.resolve()
    with tempfile.TemporaryDirectory(prefix="hermes-queue-component-") as temporary:
        state_root = Path(temporary)
        os.environ["HERMES_HOME"] = str(state_root / "home")
        os.environ["HERMES_RUNTIME_DIR"] = str(state_root / "runtime")
        sys.path.insert(0, str(source))
        try:
            store_type = importlib.import_module("hermes_state").SessionDB
            runtime = importlib.import_module("hermes_state_runtime")
            cases = []
            for case_id, (operation, expected) in CASES.items():
                root = state_root / case_id
                root.mkdir()
                cases.append(measure_case(case_id, operation, expected, root, source, store_type, runtime))
        except _RUNTIME_ERRORS as error:
            cases = [{"id": name, "status": "runtime_error", "expected": expected,
                      "observed": safe_error(error, source, state_root), "duration_ms": 0}
                     for name, (_, expected) in CASES.items()]
        print(json.dumps({
            "engine": "hermes", "source": source.name, "component": "production durable queue store",
            "timing_scope": "includes isolated SQLite initialization and case operations; excludes module loading",
            "cases": cases, "summary": {status: sum(row["status"] == status for row in cases)
                                        for status in ("pass", "fail", "runtime_error", "unsupported")},
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
