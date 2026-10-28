"""Replay fixed, authored completion/recovery probes on two actual source trees."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import tempfile

BASELINE = "789ac8778cc5c82d391dae8ffc9d2b44b86388a4"
TASK_CASES = (
    "premature_final",
    "already_complete",
    "blocked",
    "cancelled",
    "history_only",
    "budget_exhausted",
)
MCP_CASES = ("invalid_reply", "success")
MARKER = "HERMES_PROBE_RESULT="


def worker(repository: Path, category: str, case: str) -> None:
    sys.path.insert(0, str(repository))
    with tempfile.TemporaryDirectory(prefix="hermes-recovery-probe-") as directory:
        root = Path(directory)
        home = root / "profile"
        home.mkdir()
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HERMES_RUNTIME_DIR"] = str(root / "runtime")
        os.chdir(root)
        if category == "completion":
            from evals.bot_system_benchmark.task_completion import run_case

            result = run_case(case, home, root / "workspace")
        else:
            from evals.bot_system_benchmark.mcp_write_recovery import run_case

            result = run_case(case, root / "workspace")
        print(MARKER + json.dumps(result), flush=True)


def git(repository: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), *arguments], text=True, timeout=15
    ).strip()


def validate_archive(archive: Path, repository: Path) -> int:
    """Check every tracked baseline blob; added probe files do not change production."""
    entries = subprocess.check_output(
        ["git", "-C", str(repository), "ls-tree", "-rz", BASELINE], timeout=15
    ).split(b"\0")
    checked = 0
    for entry in filter(None, entries):
        metadata, name = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        if kind != "blob":
            continue
        path = archive / os.fsdecode(name)
        data = os.readlink(path).encode() if mode == "120000" else path.read_bytes()
        # .gitattributes deliberately exports PowerShell files with CRLF.
        if path.suffix == ".ps1":
            data = data.replace(b"\r\n", b"\n")
        actual = hashlib.sha1(
            f"blob {len(data)}\0".encode() + data, usedforsecurity=False
        ).hexdigest()
        if actual != expected:
            raise ValueError(
                f"Baseline archive differs from {BASELINE}: {os.fsdecode(name)}"
            )
        checked += 1
    return checked


def launch(script: Path, repository: Path, category: str, case: str) -> dict:
    allowed = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "SSL_CERT_FILE"}
    }
    allowed.update(PYTHONHASHSEED="0", PYTHONUNBUFFERED="1")
    command = [
        sys.executable,
        str(script),
        "--worker",
        "--repository",
        str(repository),
        "--category",
        category,
        "--case",
        case,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            env=allowed,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "returncode": None,
            "result": None,
            "error": "45-second subprocess deadline exceeded",
        }
    lines = completed.stdout.splitlines()
    encoded = next(
        (line[len(MARKER) :] for line in reversed(lines) if line.startswith(MARKER)),
        None,
    )
    result = json.loads(encoded) if encoded is not None else None
    # Runtime paths identify the machine, not the tested behavior.
    diagnostics = {
        "stdout": "\n".join(line for line in lines if not line.startswith(MARKER)),
        "stderr": completed.stderr,
    }
    diagnostics = {
        key: value.replace(str(repository.parent), "${WORK_ROOT}")
        for key, value in diagnostics.items()
    }
    return {
        "returncode": completed.returncode,
        "result": result,
        "error": None
        if completed.returncode == 0 and result is not None
        else "worker failed",
        **diagnostics,
    }


def run(args) -> dict:
    before, after = args.before.resolve(), args.after.resolve()
    if git(after, "status", "--porcelain"):
        raise ValueError(
            "Commit all measured source and probes before running the comparison"
        )
    checked = validate_archive(before, after)
    cases = [("completion", case) for case in TASK_CASES] + [
        ("mcp_write_recovery", case) for case in MCP_CASES
    ]
    plan = [
        (arm, category, case, repeat)
        for repeat in range(1, 4)
        for category, case in cases
        for arm in ("before", "after")
    ]
    random.Random(20261027).shuffle(plan)
    receipts = []
    for index, (arm, category, case, repeat) in enumerate(plan, 1):
        print(
            f"{index}/{len(plan)} {arm} {category}/{case} repetition={repeat}",
            flush=True,
        )
        receipt = launch(
            Path(__file__).resolve(),
            before if arm == "before" else after,
            category,
            case,
        )
        receipts.append(
            {
                "arm": arm,
                "category": category,
                "case": case,
                "repeat": repeat,
                **receipt,
            }
        )
    return {
        "protocol": "authored-fault-contracts-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "before_revision": BASELINE,
        "after_revision": git(after, "rev-parse", "HEAD"),
        "baseline_tracked_blobs_verified": checked,
        "baseline_powershell_crlf_normalized": True,
        "after_clean": True,
        "python": platform.python_version(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "model_boundary": "scripted local HTTP; no paid inference",
        "repetitions": 3,
        "planned_launches": len(plan),
        "receipts": receipts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--repository", type=Path)
    parser.add_argument("--category", choices=("completion", "mcp_write_recovery"))
    parser.add_argument("--case")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.repository, args.category, args.case)
    else:
        if not all((args.before, args.after, args.output)):
            parser.error("--before, --after and --output are required")
        args.output.write_text(json.dumps(run(args), indent=2) + "\n")


if __name__ == "__main__":
    main()
