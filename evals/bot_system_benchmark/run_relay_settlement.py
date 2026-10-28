"""Event-controlled, two-process first-settlement checks on old and new source."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

if __package__:
    from .run_bot_mode_cycle import git, verify_before
else:
    from run_bot_mode_cycle import git, verify_before


def worker(source: Path, first_error: bool) -> dict:
    sys.path.insert(0, str(source.resolve()))
    from tests.tools.test_bot_relay_settlement import _writer

    with tempfile.TemporaryDirectory(prefix="bot-settlement-") as directory:
        root = Path(directory)
        home = root / "home"
        home.mkdir()
        os.environ.update(
            HERMES_HOME=str(home), HERMES_RUNTIME_DIR=str(root / "runtime")
        )
        context = multiprocessing.get_context("spawn")
        gates = (context.Event(), context.Event(), context.Event())
        processes = [
            context.Process(
                target=_writer, args=(root, "a" * 32, first, first_error, *gates)
            )
            for first in (True, False)
        ]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=15)
            codes = [process.exitcode for process in processes]
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
        if codes != [0, 0]:
            return {
                "status": "process_error",
                "exitcodes": codes,
                "contract_pass": False,
            }
        first = (root / "first-observed.json").read_bytes()
        final = (root / "bot_relay/replies" / ("a" * 32 + ".json")).read_bytes()
        return {
            "status": "completed",
            "exitcodes": codes,
            "first_observed": json.loads(first),
            "final": json.loads(final),
            "contract_pass": first == final,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--first-error", action="store_true")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(
            "RELAY_SETTLEMENT_RESULT="
            + json.dumps(worker(args.source, args.first_error)),
            flush=True,
        )
        return
    if not all((args.before, args.after, args.output)):
        parser.error("--before, --after and --output are required")
    if git(args.after, "status", "--porcelain"):
        raise ValueError("Commit the measured implementation before running")
    checked = verify_before(args.before, args.after)
    probe = Path("tests/tools/test_bot_relay_settlement.py")
    if (args.before / probe).read_bytes() != (args.after / probe).read_bytes():
        raise ValueError("Before and after must use the same probe")
    revision = git(args.after, "rev-parse", "HEAD")
    plan = [
        (arm, error, repeat)
        for repeat in range(1, 11)
        for error in (False, True)
        for arm in ("before", "after")
    ]
    random.Random(20261027).shuffle(plan)
    report = {
        "protocol": "first-observed-reply-stability-v1",
        "state": "running",
        "planned_launches": len(plan),
        "source_revision": {
            "before": "00a8b6b290ed07026381086ff95194e9943ca6d8",
            "after": revision,
        },
        "baseline_python_blobs_verified": checked,
        "probe_sha256": hashlib.sha256(
            (args.after / "tests/tools/test_bot_relay_settlement.py").read_bytes()
        ).hexdigest(),
        "planned": [
            {"arm": arm, "first_error": error, "repeat": repeat}
            for arm, error, repeat in plan
        ],
        "launches": [],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for index, (arm, error, repeat) in enumerate(plan, 1):
        row = {
            "arm": arm,
            "first_error": error,
            "repeat": repeat,
            "status": "running",
            "admitted_utc": datetime.now(UTC).isoformat(),
        }
        report["launches"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"{index}/{len(plan)} {arm} first_error={error} repetition={repeat}",
            flush=True,
        )
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--source",
            str((args.before if arm == "before" else args.after).resolve()),
        ]
        if error:
            command.append("--first-error")
        try:
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE"}
            }
            environment.update(TZ="UTC", PYTHONHASHSEED="0")
            result = subprocess.run(
                command,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=45,
            )
            marker = "RELAY_SETTLEMENT_RESULT="
            encoded = next(
                (
                    line[len(marker) :]
                    for line in result.stdout.splitlines()
                    if line.startswith(marker)
                ),
                None,
            )
            row.update(
                status="completed"
                if result.returncode == 0 and encoded
                else "worker_error",
                returncode=result.returncode,
                result=json.loads(encoded) if encoded else None,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired:
            row.update(status="timeout", result=None)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    report["state"] = "completed"
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
