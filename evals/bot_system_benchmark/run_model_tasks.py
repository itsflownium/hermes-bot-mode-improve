"""Fixed, artifact-graded model tasks on original/new Hermes and real OpenBot/Pi."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import httpx

if __package__:
    from .model_proxy import MODEL, PortalProxy, digest
    from .model_tasks import CASES, INPUTS, PROMPTS
    from .run_bot_mode_cycle import git, verify_before
    from .run_original_baseline import ORIGINAL
    from .task_backend import runtime_metadata
else:
    from model_proxy import MODEL, PortalProxy, digest
    from model_tasks import CASES, INPUTS, PROMPTS
    from run_bot_mode_cycle import git, verify_before
    from run_original_baseline import ORIGINAL
    from task_backend import runtime_metadata


def launch(args, source: Path, arm: str, case: str, base_url: str) -> dict:
    command = [
        sys.executable,
        str(Path(__file__).with_name("model_worker.py")),
        "--arm",
        arm,
        "--case",
        case,
        "--source",
        str(source.resolve()),
        "--openbot",
        str(args.openbot.resolve()),
        "--bun",
        str(args.bun.resolve()),
        "--pi",
        str(args.pi.resolve()),
        "--base-url",
        base_url,
    ]
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE"}
    }
    if getattr(args, "precise_correction", False) and case == "user_correction":
        command.append("--precise-correction")
    environment.update(TZ="UTC", PYTHONHASHSEED="0", PYTHONUNBUFFERED="1")
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    start = time.monotonic()
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=360)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
        return {
            "status": "timeout",
            "result": None,
            "elapsed_seconds": time.monotonic() - start,
        }
    marker = "MODEL_TASK_RESULT="
    encoded = next(
        (
            line[len(marker) :]
            for line in reversed(stdout.splitlines())
            if line.startswith(marker)
        ),
        None,
    )
    return {
        "status": "completed"
        if process.returncode == 0 and encoded
        else "worker_error",
        "returncode": process.returncode,
        "result": json.loads(encoded) if encoded else None,
        "elapsed_seconds": time.monotonic() - start,
        "stderr": stderr,
        "stdout": "\n".join(
            line for line in stdout.splitlines() if not line.startswith(marker)
        ),
    }


def credentials_and_model() -> tuple[dict, dict]:
    from hermes_cli.auth_nous import resolve_nous_runtime_credentials

    credentials = resolve_nous_runtime_credentials(timeout_seconds=15)
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get(
            credentials["base_url"].rstrip("/") + "/models",
            headers={"Authorization": "Bearer " + credentials["api_key"]},
        )
    response.raise_for_status()
    model = next(row for row in response.json()["data"] if row.get("id") == MODEL)
    return credentials, {
        key: model.get(key)
        for key in ("id", "pricing", "context_length", "supported_parameters")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    args = parser.parse_args()
    if git(args.after, "status", "--porcelain"):
        raise ValueError(
            "Commit source and fixed acceptance rules before paid inference"
        )
    if os.name != "posix":
        raise ValueError("This model runner requires POSIX process-group cleanup")
    sys.path.insert(0, str(args.after.resolve()))
    checked = verify_before(args.original, args.after, ORIGINAL)
    runtime = runtime_metadata(args)
    args.output.mkdir(parents=True, exist_ok=False)
    plan = [
        (variant, case, repeat)
        for repeat in range(1, 3)
        for case in CASES
        for variant in ("hermes_original", "hermes_updated", "openbot")
    ]
    random.Random(20261027).shuffle(plan)
    credentials, model = credentials_and_model()
    report = {
        "protocol": "artifact-graded-deepseek-nous-v1",
        "state": "running",
        "paid_inference": True,
        "planned_launches": len(plan),
        "repetitions": 2,
        "model": model,
        "runtime": runtime,
        "source_revision": {
            "hermes_original": ORIGINAL,
            "hermes_updated": git(args.after, "rev-parse", "HEAD"),
            "openbot": "f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe",
        },
        "original_python_blobs_verified": checked,
        "fixture_sha256": digest({"inputs": INPUTS, "prompts": PROMPTS}),
        "planned": [
            {"variant": variant, "case": case, "repeat": repeat}
            for variant, case, repeat in plan
        ],
        "launches": [],
    }
    output = args.output / "receipts.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    with PortalProxy(credentials, model["pricing"], args.budget_ledger) as proxy:
        for index, (variant, case, repeat) in enumerate(plan, 1):
            label = f"{args.output.name}/{variant}/{case}/{repeat}"
            row = {
                "variant": variant,
                "case": case,
                "repeat": repeat,
                "launch_id": label,
                "status": "admitted",
                "admitted_utc": datetime.now(UTC).isoformat(),
            }
            report["launches"].append(row)
            output.write_text(json.dumps(report, indent=2) + "\n")
            proxy.label = label
            print(f"{index}/{len(plan)} {label}", flush=True)
            row.update(
                launch(
                    args,
                    args.original if variant == "hermes_original" else args.after,
                    "openbot" if variant == "openbot" else "hermes",
                    case,
                    proxy.base_url,
                )
            )
            row["proxy_request_count"] = sum(
                request["launch"] == label for request in proxy.ledger["requests"]
            )
            output.write_text(json.dumps(report, indent=2) + "\n")
    report.update(
        state="completed",
        runtime_source_unchanged=runtime_metadata(args) == runtime,
        original_python_blobs_unchanged=verify_before(
            args.original, args.after, ORIGINAL
        )
        == checked,
    )
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
