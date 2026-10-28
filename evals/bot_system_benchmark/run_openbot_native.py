"""Run unchanged upstream OpenBot backend E2Es with isolated state and pinned Bun."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SCRIPTS = (
    "provider-conformance-e2e",
    "provider-transcript-replay-e2e",
    "stuck-running-deliveries-e2e",
    "provider-exit-session-e2e",
    "pi-steer-e2e",
)


def attempt(source: Path, bun: Path, name: str, timeout: int) -> dict:
    report_path = source / ".openbot-build" / name / "report.json"
    previous = report_path.stat().st_mtime_ns if report_path.exists() else None
    with tempfile.TemporaryDirectory(prefix="openbot-native-eval-") as directory:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"LANG", "LC_ALL", "SSL_CERT_FILE"}
        }
        environment.update(
            HOME=directory,
            TZ="UTC",
            PATH=os.pathsep.join(
                (
                    str(bun.parent),
                    os.environ.get("BENCH_NODE_BIN", "/usr/bin"),
                    "/usr/bin",
                    "/bin",
                    "/usr/sbin",
                    "/sbin",
                )
            ),
        )
        started = time.monotonic()
        try:
            process = subprocess.run(
                [str(bun), str(source / "scripts" / f"{name}.ts")],
                cwd=source,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            row = {
                "returncode": process.returncode,
                "status": "completed",
                "stdout": process.stdout,
                "stderr": process.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "returncode": None,
                "status": "timeout",
                "report": None,
                "elapsed_seconds": time.monotonic() - started,
            }
        report = None
        if report_path.exists() and report_path.stat().st_mtime_ns != previous:
            report = json.loads(report_path.read_text())
        row.update(report=report, elapsed_seconds=time.monotonic() - started)
        row["classification"] = (
            "pass"
            if process.returncode == 0 and report and report.get("passed") is True
            else "reported_test_failure"
            if report
            else "setup_or_unreported_failure"
        )
        return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--node-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=150)
    args = parser.parse_args()
    source, bun = args.openbot.resolve(), args.bun.resolve()
    manifest = json.loads((source / "native-runtime.lock.json").read_text())
    expected = manifest["bun"]["artifacts"]["darwin-arm64"]["binarySha256"]
    actual = hashlib.sha256(bun.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            "Bun binary does not match this OpenBot revision's native-runtime lock"
        )
    os.environ["BENCH_NODE_BIN"] = str(args.node_bin.resolve())
    report = {
        "protocol": "upstream-authored-backend-e2e-v1",
        "state": "running",
        "source_revision": "f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe",
        "bun_version": manifest["bun"]["version"],
        "bun_sha256": actual,
        "model_boundary": "upstream scripted provider processes; no inference",
        "planned": list(SCRIPTS),
        "launches": [],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for name in SCRIPTS:
        row = {
            "case": name,
            "state": "running",
            "admitted_utc": datetime.now(UTC).isoformat(),
        }
        report["launches"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"START {name}", flush=True)
        row.update(attempt(source, bun, name, args.timeout), state="completed")
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"END {name}: {row.get('classification', row['status'])}", flush=True)
    report["state"] = "completed"
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
