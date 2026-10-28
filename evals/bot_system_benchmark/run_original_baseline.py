"""Run the unchanged upstream Hermes base through the already fixed artifact cases."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import random
from types import SimpleNamespace

if __package__:
    from .run_bot_mode_cycle import git, verify_before
    from .task_backend import CASES, launch
else:
    from run_bot_mode_cycle import git, verify_before
    from task_backend import CASES, launch

ORIGINAL = "c714c42431e518fcd1c8870eff5c667d5de33b57"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if git(args.repository, "status", "--porcelain"):
        raise ValueError("Commit the adapter before running")
    checked = verify_before(args.original, args.repository, ORIGINAL)
    plan = [(case, repeat) for repeat in range(1, 4) for case in CASES]
    random.Random(20261027).shuffle(plan)
    report = {
        "protocol": "original-hermes-fixed-artifact-cases-v1",
        "state": "running",
        "planned_launches": len(plan),
        "source_revision": {"hermes_original": ORIGINAL},
        "adapter_revision": git(args.repository, "rev-parse", "HEAD"),
        "original_python_blobs_verified": checked,
        "paid_inference": False,
        "surface": "bot_chat",
        "planned": [{"case": case, "repeat": repeat} for case, repeat in plan],
        "launches": [],
    }
    child = SimpleNamespace(
        hermes=args.original,
        openbot=args.openbot,
        bun=args.bun,
        pi=args.pi,
        surface="bot_chat",
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for index, (case, repeat) in enumerate(plan, 1):
        row = {
            "variant": "hermes_original",
            "case": case,
            "repeat": repeat,
            "admitted_utc": datetime.now(UTC).isoformat(),
            "status": "running",
        }
        report["launches"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{index}/{len(plan)} original/{case} repetition={repeat}", flush=True)
        row.update(launch(child, "hermes", case))
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    report.update(
        state="completed",
        original_python_blobs_unchanged=verify_before(
            args.original, args.repository, ORIGINAL
        )
        == checked,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
