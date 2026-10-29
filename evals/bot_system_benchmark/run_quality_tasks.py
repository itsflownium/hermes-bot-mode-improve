"""Fixed before/after Bot Chat quality sample; every attempt and artifact is retained."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import time

if __package__:
    from . import quality_tasks
    from .model_proxy import PortalProxy, digest
    from .model_worker import hermes
    from .run_model_tasks import credentials_and_model
else:
    import quality_tasks
    from model_proxy import PortalProxy, digest
    from model_worker import hermes
    from run_model_tasks import credentials_and_model


def git(source: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(source), *args], text=True, timeout=30).strip()


def worker(args) -> None:
    with tempfile.TemporaryDirectory(prefix="bot-quality-") as directory:
        root = Path(directory)
        (root / "profile").mkdir()
        os.environ.update(HERMES_HOME=str(root / "profile"), HERMES_RUNTIME_DIR=str(root / "runtime"))
        prompt = quality_tasks.PROMPTS[args.case] + " Work only inside this workspace; no network, installs, or delegation."
        result = hermes(args, root, [prompt], tasks=quality_tasks)
        result["runtime_completed"] = all(t.get("completed") is True and t.get("failed") is not True for t in result["turns"])
        result["contract_pass"] &= result["runtime_completed"]
        print("QUALITY_RESULT=" + json.dumps(result), flush=True)


def launch(source: Path, case: str, base_url: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE"}}
    env.update(TZ="UTC", PYTHONHASHSEED="0", PYTHONUNBUFFERED="1")
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--source", str(source), "--case", case, "--base-url", base_url]
    start = time.monotonic()
    process = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
        return {"status": "timeout", "result": None, "elapsed_seconds": time.monotonic() - start}
    marker = "QUALITY_RESULT="
    encoded = next((line[len(marker):] for line in reversed(stdout.splitlines()) if line.startswith(marker)), None)
    return {"status": "completed" if process.returncode == 0 and encoded else "worker_error",
            "returncode": process.returncode, "result": json.loads(encoded) if encoded else None,
            "elapsed_seconds": time.monotonic() - start, "stderr": stderr,
            "stdout": "\n".join(line for line in stdout.splitlines() if not line.startswith(marker))}


def run(args) -> None:
    if os.name != "posix":
        raise ValueError("Controller requires POSIX process-group cleanup; bot contracts run natively on all CI hosts")
    sources = {"before": args.before.resolve(), "after": args.after.resolve()}
    for source in sources.values():
        if git(source, "status", "--porcelain"):
            raise ValueError("Commit the implementation and fixed quality protocol before inference")
    ledger = json.loads(args.budget_ledger.read_text())
    if Decimal(ledger["authorized_cap_usd"]) != Decimal(args.authorized_cap):
        raise ValueError("Explicit authority must match the existing shared ledger")
    args.output.mkdir(parents=True, exist_ok=False)
    plan = [(arm, case, repeat) for repeat in range(1, args.repetitions + 1) for case in quality_tasks.CASES for arm in sources]
    random.Random(20261029).shuffle(plan)
    report = {"protocol": "bot-quality-before-after-v1", "state": "planned", "planned_launches": len(plan),
              "planned": plan, "repetitions": args.repetitions, "created_utc": datetime.now(UTC).isoformat(),
              "source_revisions": {arm: git(source, "rev-parse", "HEAD") for arm, source in sources.items()},
              "fixture_sha256": digest({"inputs": quality_tasks.INPUTS, "prompts": quality_tasks.PROMPTS}),
              "limits": "Two authored, unblinded cases; repetitions are fixed before inference. Native before/after Hermes Bot Chat. No OpenBot run or general quality ranking. Prose requires separate manual review.",
              "launches": []}
    receipt = args.output / "receipts.json"
    def save():
        receipt.write_text(json.dumps(report, indent=2) + "\n")
    save()
    sys.path.insert(0, str(sources["after"]))
    credentials, model = credentials_and_model()
    report["model"] = model
    with PortalProxy(credentials, model["pricing"], args.budget_ledger,
                     reservation_ceiling=args.reservation_ceiling or args.authorized_cap,
                     authorized_cap=args.authorized_cap, request_limit=500) as proxy:
        for arm, case, repeat in plan:
            proxy.label = f"bot-quality-before-after-v1/{arm}/{case}/{repeat}"
            row = {"arm": arm, "case": case, "repeat": repeat, "launch_id": proxy.label,
                   "status": "admitted", "admitted_utc": datetime.now(UTC).isoformat()}
            report["launches"].append(row)
            save()
            row.update(launch(sources[arm], case, proxy.base_url))
            save()
            print(json.dumps({k: row[k] for k in ("arm", "case", "repeat", "status")}
                             | {"pass": (row.get("result") or {}).get("contract_pass", False)}), flush=True)
    report["state"] = "completed"
    save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--case", choices=quality_tasks.CASES)
    parser.add_argument("--base-url")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--budget-ledger", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorized-cap", default="5.00")
    parser.add_argument("--reservation-ceiling")
    parser.add_argument("--repetitions", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    needed = ("source", "case", "base_url") if args.worker else ("before", "after", "budget_ledger", "output")
    if any(getattr(args, key) is None for key in needed):
        parser.error("Missing arguments: " + ", ".join(needed))
    worker(args) if args.worker else run(args)


if __name__ == "__main__":
    main()
