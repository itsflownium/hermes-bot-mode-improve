"""Compare previous/new Bot Chat behavior and unchanged OpenBot on fixed artifact cases."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import random
from types import SimpleNamespace
import subprocess

if __package__:
    from .task_backend import CASES, launch, runtime_metadata
else:
    from task_backend import CASES, launch, runtime_metadata

BASELINE = "00a8b6b290ed07026381086ff95194e9943ca6d8"


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True, timeout=15
    ).strip()


def verify_before(archive: Path, repository: Path, revision: str = BASELINE) -> int:
    entries = subprocess.check_output(
        ["git", "-C", str(repository), "ls-tree", "-rz", revision], timeout=15
    )
    checked = 0
    for entry in filter(None, entries.split(b"\0")):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        if kind != "blob" or not raw_path.endswith(b".py"):
            continue
        path = archive / os.fsdecode(raw_path)
        data = os.readlink(path).encode() if mode == "120000" else path.read_bytes()
        actual = hashlib.sha1(
            f"blob {len(data)}\0".encode() + data, usedforsecurity=False
        ).hexdigest()
        if actual != expected:
            raise ValueError(f"Baseline Python source differs: {os.fsdecode(raw_path)}")
        checked += 1
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if git(args.after, "status", "--porcelain"):
        raise ValueError("Commit the measured implementation before running")
    checked = verify_before(args.before, args.after)
    metadata = runtime_metadata(args)
    plan = [
        (variant, case, repeat)
        for repeat in range(1, 4)
        for case in CASES
        for variant in ("hermes_before", "hermes_after", "openbot")
    ]
    random.Random(20261027).shuffle(plan)
    report = {
        "protocol": "bot-mode-completion-cycle-v1",
        "state": "running",
        "planned_launches": len(plan),
        "source_revision": {
            "hermes_before": BASELINE,
            "hermes_after": git(args.after, "rev-parse", "HEAD"),
            "openbot": "f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe",
        },
        "baseline_python_blobs_verified": checked,
        "runtime": metadata,
        "paid_inference": False,
        "planned": [
            {"variant": variant, "case": case, "repeat": repeat}
            for variant, case, repeat in plan
        ],
        "launches": [],
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for index, (variant, case, repeat) in enumerate(plan, 1):
        row = {
            "variant": variant,
            "case": case,
            "repeat": repeat,
            "admitted_utc": datetime.now(UTC).isoformat(),
            "status": "running",
        }
        report["launches"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{index}/{len(plan)} {variant}/{case} repetition={repeat}", flush=True)
        child = SimpleNamespace(
            hermes=args.before if variant == "hermes_before" else args.after,
            openbot=args.openbot,
            bun=args.bun,
            pi=args.pi,
            surface="bot_chat",
        )
        row.update(launch(child, "openbot" if variant == "openbot" else "hermes", case))
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    report.update(
        state="completed", runtime_source_unchanged=runtime_metadata(args) == metadata
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
