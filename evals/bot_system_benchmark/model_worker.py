"""One isolated real-model task using native Hermes or OpenBot/Pi execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    from .model_proxy import MODEL, MAX_OUTPUT
    from .model_tasks import (
        CASES,
        INPUTS,
        OFFLINE,
        PRECISE_CORRECTION,
        PROMPTS,
        grade,
        seed,
    )
else:
    from model_proxy import MODEL, MAX_OUTPUT
    from model_tasks import (
        CASES,
        INPUTS,
        OFFLINE,
        PRECISE_CORRECTION,
        PROMPTS,
        grade,
        seed,
    )


def hermes(args, root: Path, prompts: list[str]) -> dict:
    sys.path.insert(0, str(args.source.resolve()))
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
    from utils import atomic_json_write
    from tests.fakes.fake_llm_provider import write_hermes_home

    home, workspace = root / "profile", root / "workspace"
    seed(workspace, args.case)
    write_hermes_home(
        home, args.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
    )
    # The credential remains in the parent proxy; both native runtimes use a local dummy key.
    atomic_json_write(
        home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Evaluation"}}}
    )
    database = SessionDB(db_path=home / "state.db")
    database.create_session("model-eval", "desktop")
    database.set_session_title("model-eval", "Bot Chat")
    os.chdir(workspace)
    agent = AIAgent(
        model=MODEL,
        provider="custom",
        api_key="fixture-local-only",
        base_url=args.base_url,
        api_mode="chat_completions",
        enabled_toolsets=["file", "terminal", "todo"],
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        skip_background_review=True,
        save_trajectories=False,
        max_iterations=16,
        max_tokens=MAX_OUTPUT,
        reasoning_config={"enabled": False},
        run_budget_seconds=150,
        request_overrides={"timeout": 75},
        fallback_model={},
        cwd=str(workspace),
        session_db=database,
        session_id="model-eval",
        platform="desktop",
    )
    agent.client.max_retries = 0
    history, turns = [], []
    try:
        for prompt in prompts:
            result = agent.run_conversation(
                prompt, conversation_history=history, task_id="model-eval"
            )
            history = result.get("messages", [])
            turns.append(
                {
                    key: result.get(key)
                    for key in (
                        "final_response",
                        "failed",
                        "completed",
                        "task_checklist",
                        "task_completion_review",
                    )
                }
            )
        grading = grade(workspace, args.case)
        grading["runtime_completed"] = all(
            row.get("failed") is not True for row in turns
        )
        grading["contract_pass"] &= grading["runtime_completed"]
        return {"turns": turns, **grading}
    finally:
        agent.close()
        database.close()


def openbot(args, root: Path, prompts: list[str]) -> dict:
    request = {
        "repository": str(args.openbot.resolve()),
        "state_directory": str(root),
        "pi_executable": str(args.pi.resolve()),
        "base_url": args.base_url,
        "model_id": "deepseek-v4.1-flash",
        "max_tokens": MAX_OUTPUT,
        "prompts": prompts,
        "fixture_files": INPUTS[args.case],
        "return_workspace": True,
        "request_timeout_ms": 75000,
        "turn_timeout_ms": 150000,
    }
    process = subprocess.run(
        [str(args.bun.resolve()), str(Path(__file__).with_name("task_openbot.mts"))],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=root,
        timeout=330,
        check=False,
    )
    marker = "OPENBOT_TASK_RESULT="
    encoded = next(
        (
            line[len(marker) :]
            for line in process.stdout.splitlines()
            if line.startswith(marker)
        ),
        None,
    )
    if process.returncode != 0 or encoded is None:
        return {
            "status": "worker_error",
            "returncode": process.returncode,
            "stderr": process.stderr,
            "stdout": process.stdout,
            "contract_pass": False,
        }
    result = json.loads(encoded)
    workspace = Path(result.pop("workspace_path"))
    grading = grade(workspace, args.case)
    grading["runtime_completed"] = all(
        row.get("status") == "completed" for row in result["terminals"]
    )
    grading["contract_pass"] &= grading["runtime_completed"]
    return {"backend": result, **grading}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("hermes", "openbot"), required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--precise-correction", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="real-model-task-") as directory:
        root = Path(directory)
        (root / "home").mkdir()
        (root / "profile").mkdir()
        os.environ.update(
            HOME=str(root / "home"),
            HERMES_HOME=str(root / "profile"),
            HERMES_RUNTIME_DIR=str(root / "runtime"),
        )
        selected = (
            PRECISE_CORRECTION
            if args.precise_correction and args.case == "user_correction"
            else PROMPTS[args.case]
        )
        prompts = [prompt + OFFLINE for prompt in selected]
        result = (
            hermes(args, root, prompts)
            if args.arm == "hermes"
            else openbot(args, root, prompts)
        )
        print("MODEL_TASK_RESULT=" + json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
