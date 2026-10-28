"""Fixed follow-up after the initial model run; preserve its tasks and every failure."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import random
import sys

if __package__:
    from .model_proxy import PortalProxy, digest
    from .model_tasks import CASES, INPUTS, PRECISE_CORRECTION, PROMPTS
    from .run_bot_mode_cycle import git, verify_before
    from .run_model_tasks import credentials_and_model, launch
    from .task_backend import runtime_metadata
else:
    from model_proxy import PortalProxy, digest
    from model_tasks import CASES, INPUTS, PRECISE_CORRECTION, PROMPTS
    from run_bot_mode_cycle import git, verify_before
    from run_model_tasks import credentials_and_model, launch
    from task_backend import runtime_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--before-revision", required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--protocol", choices=("readback", "terminal"), default="readback"
    )
    args = parser.parse_args()
    if git(args.after, "status", "--porcelain"):
        raise ValueError("Commit the source and follow-up plan before inference")
    sys.path.insert(0, str(args.after.resolve()))
    checked = verify_before(args.before, args.after, args.before_revision)
    runtime = runtime_metadata(args)
    plan = [("hermes_after", case, repeat) for repeat in range(1, 3) for case in CASES]
    plan += [
        (variant, case, 1)
        for variant in ("hermes_before", "openbot")
        for case in ("data_summary", "user_correction")
    ]
    args.precise_correction = args.protocol == "terminal"
    selected_prompts = PROMPTS
    if args.precise_correction:
        plan = [
            (variant, case, 1)
            for variant in ("hermes_after", "openbot")
            for case in CASES
        ]
        plan.append(("hermes_before", "transient_recovery", 1))
        selected_prompts = {**PROMPTS, "user_correction": PRECISE_CORRECTION}
    random.Random(20261029 if args.precise_correction else 20261028).shuffle(plan)
    args.output.mkdir(parents=True, exist_ok=False)
    credentials, model = credentials_and_model()
    report = {
        "protocol": "model-terminal-explicit-schema-v1"
        if args.precise_correction
        else "model-readback-followup-v1",
        "state": "running",
        "planned_launches": len(plan),
        "model": model,
        "runtime": runtime,
        "paid_inference": True,
        "source_revision": {
            "hermes_before": args.before_revision,
            "hermes_after": git(args.after, "rev-parse", "HEAD"),
            "openbot": "f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe",
        },
        "before_python_blobs_verified": checked,
        "fixture_sha256": digest({"inputs": INPUTS, "prompts": selected_prompts}),
        "planned": [
            {"variant": variant, "case": case, "repeat": repeat}
            for variant, case, repeat in plan
        ],
        "launches": [],
    }
    output = args.output / "receipts.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    guards = (
        {"reservation_ceiling": "4.95", "request_limit": 500}
        if args.precise_correction
        else {}
    )
    with PortalProxy(
        credentials, model["pricing"], args.budget_ledger, **guards
    ) as proxy:
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
            source = args.before if variant == "hermes_before" else args.after
            row.update(
                launch(
                    args,
                    source,
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
        before_python_blobs_unchanged=verify_before(
            args.before, args.after, args.before_revision
        )
        == checked,
    )
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
