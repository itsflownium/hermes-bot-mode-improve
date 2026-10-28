"""Run equal-input production-component comparisons without model or network calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

if __package__:
    from .fixtures import cases, catalog, fixture_digest, additional_cases
else:
    from fixtures import cases, catalog, fixture_digest, additional_cases

HERE = Path(__file__).resolve().parent
QUEUE_CASE_IDS = frozenset(
    {
        "queue_fifo",
        "queued_cancel_survives_reopen",
        "active_cancel_refused",
        "restart_queued_retained",
        "active_restart_honest",
        "recipient_separation",
        "duplicate_replay",
    }
)


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[
        max(0, min(len(ordered) - 1, int(len(ordered) * quantile + 0.999999) - 1))
    ]


def validate_result(actual: dict, schemas: dict[str, dict]) -> None:
    names = actual["names"]
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("adapter returned invalid names")
    if len(names) > 5 or len(set(names)) != len(names):
        raise ValueError("adapter must return at most five unique names")
    returned = actual.get("schemas", {})
    if set(returned) != set(actual.get("schema_names", [])) or not set(
        returned
    ).issubset(names):
        raise ValueError("schema names must belong to returned results")
    for name, schema in returned.items():
        if name not in schemas or json.dumps(
            schema, sort_keys=True, allow_nan=False
        ) != json.dumps(schemas[name], sort_keys=True, allow_nan=False):
            raise ValueError("adapter altered or truncated a parameter schema")
    samples = actual.get("latencies_ms", [])
    if not samples or any(
        type(value) not in (float, int) or not math.isfinite(value) or value < 0
        for value in samples
    ):
        raise ValueError("adapter omitted valid timing samples")


def discovery_score(
    observed: dict, expected: list[dict], schemas: dict[str, dict]
) -> dict:
    rows = observed.get("results", [])
    if len(rows) != len(expected) or any(
        actual.get("query") != case["query"] for actual, case in zip(rows, expected)
    ):
        raise ValueError("adapter did not return every case in the requested order")
    groups: dict[str, dict] = {}
    latencies = []
    judgments = []
    for actual, case in zip(rows, expected):
        validate_result(actual, schemas)
        names = actual["names"]
        accepted = set(case["acceptable"])
        top1 = bool(names and names[0] in accepted)
        hit = bool(accepted.intersection(names))
        passed = not names if case["expect_empty"] else hit
        ready = bool(accepted.intersection(actual.get("schema_names", [])))
        group = groups.setdefault(
            case["group"],
            {"cases": 0, "passed": 0, "top1": 0, "schema_ready": 0, "returned": 0},
        )
        group["cases"] += 1
        group["passed"] += int(passed)
        group["top1"] += int(top1)
        group["schema_ready"] += int(ready)
        group["returned"] += int(bool(names))
        samples = actual.get("latencies_ms", [])
        latencies.extend(samples)
        judgments.append(
            {"id": case["id"], "passed": passed, "top1": top1, "schema_ready": ready}
        )
    return {
        "cases": len(expected),
        "passed": sum(row["passed"] for row in judgments),
        "groups": groups,
        "p50_ms": statistics.median(latencies),
        "p95_ms": percentile(latencies, 0.95),
        "judgments": judgments,
    }


def clean_environment(home: str) -> dict[str, str]:
    # Deliberately do not inherit credentials or product config into either arm.
    keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TMPDIR",
        "TEMP",
        "TMP",
    )
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update(
        {
            "HOME": home,
            "USERPROFILE": home,
            "HERMES_HOME": str(Path(home) / "hermes"),
            "LANG": "C.UTF-8",
            "TZ": "UTC",
            "PYTHONHASHSEED": "0",
            "NO_COLOR": "1",
            "DO_NOT_TRACK": "1",
            "TERMINAL_ENV": "local",
        }
    )
    return env


def queue_score(observed: dict) -> dict:
    rows = observed["cases"]
    if (
        len(rows) != len(QUEUE_CASE_IDS)
        or {row["id"] for row in rows} != QUEUE_CASE_IDS
    ):
        raise ValueError("queue adapter must report each declared case exactly once")
    counts = {status: 0 for status in ("pass", "fail", "runtime_error", "unsupported")}
    for row in rows:
        if row["status"] not in counts:
            raise ValueError("queue adapter returned an unknown outcome")
        counts[row["status"]] += 1
    return {"cases": len(rows), **counts}


def checkpoint(path: Path, report: dict) -> None:
    """Persist admissions and outcomes so a killed run leaves an honest denominator."""
    report["launches"] = len(report["discovery"]) + len(report["queue"])
    report["completed_launches"] = sum(
        row["status"] == "completed"
        for group in ("discovery", "queue")
        for row in report[group]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def invoke(command: list[str], payload: dict | None = None, timeout: int = 180) -> dict:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="bot-component-bench-") as home:
        (Path(home) / "hermes").mkdir()
        try:
            process = subprocess.run(
                command,
                input=json.dumps(payload) if payload is not None else None,
                text=True,
                capture_output=True,
                timeout=timeout,
                env=clean_environment(home),
                cwd=home,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "wall_s": time.perf_counter() - started}
        except OSError as exc:
            return {
                "status": "runtime_error",
                "detail": exc.strerror,
                "wall_s": time.perf_counter() - started,
            }
        if process.returncode:
            # Retain failure evidence, but strip the private local paths from published receipts.
            detail = process.stderr[-6000:]
            for value in (str(Path.home()), home):
                detail = detail.replace(value, "<local>")
            return {
                "status": "runtime_error",
                "exit_code": process.returncode,
                "detail": detail,
                "wall_s": time.perf_counter() - started,
            }
        try:
            data = json.loads(process.stdout)
        except (ValueError, TypeError):
            return {"status": "invalid_output", "wall_s": time.perf_counter() - started}
        if isinstance(data, dict):
            data.pop("repository_path", None)
    return {
        "status": "completed",
        "wall_s": time.perf_counter() - started,
        "data": data,
    }


def source_metadata(source: Path, revision: str | None) -> dict:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    resolved = result.stdout.strip() if result.returncode == 0 else revision
    if not resolved or len(resolved) != 40:
        raise ValueError("each source needs a full revision or a Git checkout")
    if revision and resolved != revision:
        raise ValueError("source revision differs from requested revision")
    if result.returncode:
        return {
            "revision": resolved,
            "provenance": "declared_source_archive",
            "tracked_changes": None,
            "untracked_entries": None,
        }
    changes = subprocess.run(
        ["git", "-C", str(source), "diff", "HEAD", "--quiet", "--exit-code"],
        capture_output=True,
        check=False,
        timeout=10,
    )
    untracked = subprocess.run(
        ["git", "-C", str(source), "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return {
        "revision": resolved,
        "provenance": "git_checkout",
        "tracked_changes": changes.returncode == 1,
        "untracked_entries": len(untracked.stdout.splitlines()),
    }


def adapter_hashes() -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(HERE.iterdir())
        if path.suffix in {".py", ".ts"}
    }


def run(args: argparse.Namespace) -> dict:
    arms = {
        "hermes_before": (Path(args.before_source).resolve(), args.before_revision),
        "hermes_after": (Path(args.hermes_source).resolve(), args.hermes_revision),
        "openbot": (Path(args.openbot_source).resolve(), args.openbot_revision),
    }
    commands = {
        "hermes_before": [args.python, str(HERE / "discovery_hermes.py")],
        "hermes_after": [args.python, str(HERE / "discovery_hermes.py")],
        "openbot": [
            args.node,
            "--import",
            args.tsx_loader,
            str(HERE / "discovery_openbot.ts"),
        ],
    }
    report = {
        "schema_version": 1,
        "track": "offline_production_components",
        "temporary_profile": "existing_empty_directory",
        "started_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "seed": args.seed,
        "repetitions": args.repetitions,
        "queue_repetitions": args.queue_repetitions,
        "catalog_sizes": args.sizes,
        "expected_launches": (len(args.sizes) + args.queue_repetitions) * len(arms),
        "run_status": "running",
        "sources": {
            name: source_metadata(source, revision)
            for name, (source, revision) in arms.items()
        },
        "adapter_sha256": adapter_hashes(),
        "discovery": [],
        "queue": [],
        "case_sets": {
            "initial": len(cases()),
            "additional_request_variants": len(additional_cases()),
        },
        "not_measured": [
            "model reasoning or task completion",
            "token or monetary cost",
            "desktop/mobile UX",
            "real provider reconnect",
            "external side effects",
        ],
    }
    report["node"] = subprocess.run(
        [args.node, "--version"], check=True, text=True, capture_output=True, timeout=10
    ).stdout.strip()
    report["tsx"] = json.loads(
        (Path(args.tsx_loader).parent.parent / "package.json").read_text()
    )["version"]
    checkpoint(args.output, report)
    rng = random.Random(args.seed)
    evaluation_cases = cases() + additional_cases()
    for size in args.sizes:
        order = list(arms)
        rng.shuffle(order)
        for name in order:
            request = {
                "repository_path": str(arms[name][0]),
                "catalog": catalog(size),
                "queries": [case["query"] for case in evaluation_cases],
                "limit": 5,
                "warmups": 2,
                "repetitions": args.repetitions,
            }
            row = {
                "arm": name,
                "catalog_size": size,
                "fixture_sha256": fixture_digest(size),
                "status": "running",
            }
            report["discovery"].append(row)
            checkpoint(args.output, report)
            result = invoke(commands[name], request)
            row.update(result)
            if result["status"] == "completed":
                try:
                    row["score"] = discovery_score(
                        result["data"],
                        evaluation_cases,
                        {
                            entry["name"]: entry["parameters"]
                            for entry in request["catalog"]
                        },
                    )
                except (KeyError, ValueError, TypeError) as exc:
                    row["status"] = "invalid_output"
                    row["detail"] = str(exc)
            checkpoint(args.output, report)
    for repetition in range(args.queue_repetitions):
        order = list(arms)
        rng.shuffle(order)
        for name in order:
            if name == "openbot":
                command = [
                    args.node,
                    "--import",
                    args.tsx_loader,
                    str(HERE / "queue_openbot.ts"),
                ]
            else:
                command = [args.python, str(HERE / "queue_hermes.py")]
            row = {"arm": name, "repetition": repetition, "status": "running"}
            report["queue"].append(row)
            checkpoint(args.output, report)
            result = invoke(command + ["--source", str(arms[name][0])])
            row.update(result)
            if result["status"] == "completed":
                try:
                    row["score"] = queue_score(result["data"])
                except (KeyError, ValueError, TypeError) as exc:
                    row["status"] = "invalid_output"
                    row["detail"] = str(exc)
            checkpoint(args.output, report)
    report["run_status"] = (
        "completed"
        if report["completed_launches"] == report["expected_launches"]
        else "completed_with_errors"
    )
    checkpoint(args.output, report)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", required=True)
    parser.add_argument("--hermes-revision")
    parser.add_argument("--before-source", required=True)
    parser.add_argument("--before-revision", required=True)
    parser.add_argument("--openbot-source", required=True)
    parser.add_argument("--openbot-revision")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", required=True)
    parser.add_argument("--tsx-loader", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=15)
    parser.add_argument("--queue-repetitions", type=int, default=3)
    parser.add_argument(
        "--sizes",
        type=lambda value: [int(item) for item in value.split(",")],
        default=[32, 256, 1024],
    )
    parser.add_argument("--seed", type=int, default=20261027)
    args = parser.parse_args()
    if (
        args.repetitions < 1
        or args.queue_repetitions < 1
        or any(size < 32 for size in args.sizes)
    ):
        parser.error(
            "positive repetitions and catalog sizes of at least 32 are required"
        )
    if args.output.exists():
        parser.error(
            "output already exists; use a new receipt path to retain prior attempts"
        )
    return args


def main() -> None:
    args = parse_args()
    report = run(args)
    checkpoint(args.output, report)
    print(
        json.dumps(
            {
                "launches": report["launches"],
                "completed": report["completed_launches"],
                "discovery": [
                    {k: row[k] for k in ("arm", "catalog_size", "status")}
                    | {
                        "score": {
                            key: value
                            for key, value in row.get("score", {}).items()
                            if key in {"cases", "passed", "p50_ms", "p95_ms"}
                        }
                    }
                    for row in report["discovery"]
                ],
            },
            indent=2,
        )
    )
    if report["completed_launches"] != report["expected_launches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
