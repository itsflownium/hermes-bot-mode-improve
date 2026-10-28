"""Matched backend artifact probes, using real runtimes and scripted local HTTP."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
CASES = (
    "complete_files",
    "premature_final",
    "blocked",
    "cancelled",
    "status_only",
    "write_error_recovery",
)
PROMPTS = {
    "complete_files": "Create report.txt containing REPORT and attachment.txt containing ATTACHMENT in your workspace.",
    "premature_final": "Create report.txt containing REPORT and attachment.txt containing ATTACHMENT in your workspace.",
    "blocked": "The needed source data has not been provided. Explain the blocker; do not create output files.",
    "cancelled": "Cancel the report and attachment request. Do not create any output files.",
    "status_only": "Only check whether report.txt exists. Do not change or create any files.",
    "write_error_recovery": "Create report.txt containing REPORT and attachment.txt containing ATTACHMENT. If a file operation fails, correct the path and continue.",
}


def scripts(arm: str, case: str):
    from tests.fakes.fake_llm_provider import Text, ToolCall

    writer, reader = (
        ("write", "read") if arm == "openbot" else ("write_file", "read_file")
    )
    report = ToolCall(writer, {"path": "report.txt", "content": "REPORT"})
    attachment = ToolCall(writer, {"path": "attachment.txt", "content": "ATTACHMENT"})
    done = Text("All deliverables are done.")
    return {
        "complete_files": [report, attachment, done],
        "premature_final": [report, done, attachment, done],
        "blocked": [
            Text("Blocked: the source data is missing. No output files were created.")
        ],
        "cancelled": [Text("Cancelled as requested. No output files were created.")],
        "status_only": [
            ToolCall(reader, {"path": "report.txt"}),
            Text("report.txt exists; no files were changed."),
        ],
        "write_error_recovery": [
            ToolCall(writer, {"path": ".", "content": "INVALID_DIRECTORY_WRITE"}),
            report,
            attachment,
            done,
        ],
    }[case]


def grade(case: str, outputs: dict, text: str, tool_results: list) -> dict:
    files_complete = outputs == {"report.txt": "REPORT", "attachment.txt": "ATTACHMENT"}
    no_files = all(value is None for value in outputs.values())
    first_error = str(tool_results[0]).lower() if tool_results else ""
    error_visible = any(
        marker in first_error for marker in ('"error"', "eisdir", "error:")
    )
    accepted = {
        "complete_files": files_complete,
        "premature_final": files_complete,
        "blocked": no_files and "blocked" in text.lower(),
        "cancelled": no_files and "cancelled" in text.lower(),
        "status_only": outputs == {"report.txt": "ORIGINAL", "attachment.txt": None},
        "write_error_recovery": files_complete and error_visible,
    }[case]
    return {
        "contract_pass": accepted,
        "files_complete": files_complete,
        "first_tool_error_visible": error_visible
        if case == "write_error_recovery"
        else None,
    }


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def wire_observations(requests: list[dict]) -> dict:
    # Do not redistribute production prompts or record HTTP authentication headers.
    bodies = [row["body"] for row in requests]
    tool_results = [
        message.get("content")
        for body in bodies
        for message in body.get("messages", [])
        if message.get("role") == "tool"
    ]
    return {
        "request_count": len(bodies),
        "main_request_count": sum(bool(body.get("tools")) for body in bodies),
        "tool_results": tool_results,
        "requests": [
            {
                "body_sha256": digest(body),
                "model": body.get("model"),
                "roles": [message.get("role") for message in body.get("messages", [])],
                "message_sha256": [
                    digest(message) for message in body.get("messages", [])
                ],
                "tools_sha256": digest(body.get("tools")),
                "tool_names": [
                    item.get("function", {}).get("name")
                    for item in body.get("tools", [])
                ],
                "tool_calls": [
                    message.get("tool_calls")
                    for message in body.get("messages", [])
                    if message.get("tool_calls")
                ],
            }
            for body in bodies
        ],
    }


def hermes_turn(root: Path, case: str, base_url: str, surface: str = "core") -> dict:
    from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
    from tests.fakes.fake_llm_provider import write_hermes_home
    from run_agent import AIAgent

    home, workspace = root / "profile", root / "workspace"
    workspace.mkdir()
    write_hermes_home(
        home, base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
    )
    os.chdir(workspace)
    if case == "status_only":
        (workspace / "report.txt").write_text("ORIGINAL")
    database = None
    session_options = {}
    if surface == "bot_chat":
        from hermes_state import SessionDB
        from utils import atomic_json_write

        atomic_json_write(
            home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Fixture"}}}
        )
        database = SessionDB(db_path=home / "state.db")
        session_id = "matched-bot-chat"
        database.create_session(session_id, "desktop")
        database.set_session_title(session_id, "Bot Chat")
        session_options = {
            "session_db": database,
            "session_id": session_id,
            "platform": "desktop",
        }
    agent = AIAgent(
        provider="custom",
        base_url=base_url,
        api_key="fixture-local-only",
        model="scripted",
        enabled_toolsets=["todo", "file"],
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        skip_background_review=True,
        save_trajectories=False,
        max_iterations=10,
        max_tokens=2048,
        cwd=str(workspace),
        fallback_model={},
        **session_options,
    )
    agent.client.max_retries = 0
    try:
        result = agent.run_conversation(
            PROMPTS[case], conversation_history=[], task_id="matched-backend"
        )
        outputs = {
            name: (workspace / name).read_text()
            if (workspace / name).exists()
            else None
            for name in ("report.txt", "attachment.txt")
        }
        return {
            "outputs": outputs,
            "final_response": result.get("final_response"),
            "failed": result.get("failed"),
            "checklist": result.get("task_checklist"),
            "completion_review": result.get("task_completion_review"),
            "surface": surface,
            "execution": "real AIAgent + real native file tools; no preloaded checklist",
        }
    finally:
        agent.close()
        if database is not None:
            database.close()


def openbot_turn(args, root: Path, case: str, base_url: str) -> dict:
    request = {
        "repository": str(args.openbot.resolve()),
        "state_directory": str(root),
        "pi_executable": str(args.pi.resolve()),
        "base_url": base_url,
        "prompt": PROMPTS[case],
        "seed_status_file": case == "status_only",
    }
    process = subprocess.run(
        [str(args.bun.resolve()), str(HERE / "task_openbot.mts")],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        cwd=root,
        timeout=80,
        check=False,
    )
    encoded = next(
        (
            line.split("=", 1)[1]
            for line in process.stdout.splitlines()
            if line.startswith("OPENBOT_TASK_RESULT=")
        ),
        None,
    )
    if process.returncode != 0 or encoded is None:
        raise RuntimeError(
            f"OpenBot backend worker did not return a receipt: {process.stderr[-3000:]}"
        )
    result = json.loads(encoded)
    result["final_response"] = "\n".join(
        message["text"]
        for message in result["messages"]
        if message["author"] == "assistant"
    )
    return result


def worker(args) -> dict:
    sys.path.insert(0, str(args.hermes.resolve()))
    with tempfile.TemporaryDirectory(prefix="matched-backend-") as directory:
        root = Path(directory)
        home = root / "profile"
        home.mkdir()
        os.environ.update(
            HOME=str(root / "home"),
            HERMES_HOME=str(home),
            HERMES_RUNTIME_DIR=str(root / "runtime"),
        )
        from tests.fakes.fake_llm_provider import FakeLLMServer, Text

        responses = scripts(args.arm, args.case)
        steps = iter(responses)
        served = []
        setup_errors = []

        def respond(record):
            if len(served) >= 12:
                setup_errors.append("Twelve-response fixture ceiling exceeded")
                return Text("FIXTURE_REQUEST_CEILING")
            response = next(steps, responses[-1])
            served.append(type(response).__name__)
            name = getattr(response, "name", None)
            available = {
                tool.get("function", {}).get("name")
                for tool in record["body"].get("tools", [])
            }
            if name is not None and name not in available:
                setup_errors.append(f"Fixture tried an unadvertised tool: {name}")
            return response

        with FakeLLMServer(respond) as server:
            observed = (
                hermes_turn(root, args.case, server.base_url, args.surface)
                if args.arm == "hermes"
                else openbot_turn(args, root, args.case, server.base_url)
            )
            wire = wire_observations(server.requests)
            return {
                "case": args.case,
                "arm": args.arm,
                "observed": observed,
                "wire": wire,
                "setup_errors": setup_errors,
                "scripted_responses": served,
                **grade(
                    args.case,
                    observed["outputs"],
                    observed.get("final_response") or "",
                    wire["tool_results"],
                ),
            }


def launch(args, arm: str, case: str) -> dict:
    allowed = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE"}
    }
    allowed.update(TZ="UTC", PYTHONHASHSEED="0", PYTHONUNBUFFERED="1")
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--arm",
        arm,
        "--case",
        case,
        "--surface",
        getattr(args, "surface", "core"),
        "--hermes",
        str(args.hermes.resolve()),
        "--openbot",
        str(args.openbot.resolve()),
        "--bun",
        str(args.bun.resolve()),
        "--pi",
        str(args.pi.resolve()),
    ]
    try:
        process = subprocess.run(
            command,
            env=allowed,
            text=True,
            capture_output=True,
            timeout=100,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "process_timeout", "returncode": None, "result": None}
    marker = "MATCHED_BACKEND_RESULT="
    encoded = next(
        (
            line[len(marker) :]
            for line in reversed(process.stdout.splitlines())
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
        "stdout": "\n".join(
            line for line in process.stdout.splitlines() if not line.startswith(marker)
        ),
        "stderr": process.stderr,
    }


def run(args) -> None:
    revision = subprocess.check_output(
        ["git", "-C", str(args.hermes), "rev-parse", "HEAD"], text=True, timeout=15
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(args.hermes), "status", "--porcelain"], text=True, timeout=15
    ).strip()
    if dirty:
        raise ValueError("Commit the measured source and adapters before running")
    metadata = runtime_metadata(args)
    plan = [
        (arm, case, repeat)
        for repeat in range(1, 4)
        for case in CASES
        for arm in ("hermes", "openbot")
    ]
    random.Random(20261027).shuffle(plan)
    report = {
        "protocol": "matched-native-backend-artifacts-v1",
        "state": "running",
        "planned_launches": len(plan),
        "paid_inference": False,
        "hermes_surface": args.surface,
        "source_revision": {
            "hermes": revision,
            "openbot": "f91535fb0c8d6fd0a63911ec6e4b67154fd85ebe",
        },
        "planned": [
            {"arm": arm, "case": case, "repeat": repeat} for arm, case, repeat in plan
        ],
        "launches": [],
        "runtime": metadata,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for index, (arm, case, repeat) in enumerate(plan, 1):
        row = {
            "arm": arm,
            "case": case,
            "repeat": repeat,
            "admitted_utc": datetime.now(UTC).isoformat(),
            "status": "running",
        }
        report["launches"].append(row)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{index}/{len(plan)} {arm}/{case} repetition={repeat}", flush=True)
        row.update(launch(args, arm, case))
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    unchanged = runtime_metadata(args) == metadata
    report.update(state="completed", runtime_source_unchanged=unchanged)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


def runtime_metadata(args) -> dict:
    root = args.openbot.resolve()
    manifest = json.loads((root / "native-runtime.lock.json").read_text())
    bun_hash = hashlib.sha256(args.bun.read_bytes()).hexdigest()
    pi_hash = hashlib.sha256(args.pi.read_bytes()).hexdigest()
    if bun_hash != manifest["bun"]["artifacts"]["darwin-arm64"]["binarySha256"]:
        raise ValueError("Bun does not match the pinned native runtime")
    if pi_hash != manifest["pi"]["artifacts"]["darwin-arm64"]["files"]["bin/pi"]:
        raise ValueError("Pi does not match the pinned native runtime")
    files = {}
    for pattern in ("src/backend/**/*.ts", "packages/*/src/**/*.ts"):
        for path in sorted(root.glob(pattern)):
            files[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return {
        "bun_version": manifest["bun"]["version"],
        "bun_sha256": bun_hash,
        "pi_version": manifest["pi"]["version"],
        "pi_sha256": pi_hash,
        "openbot_source_files": files,
        "openbot_source_digest": digest(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--arm", choices=("hermes", "openbot"))
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--surface", choices=("core", "bot_chat"), default="core")
    parser.add_argument("--hermes", type=Path, required=True)
    parser.add_argument("--openbot", type=Path, required=True)
    parser.add_argument("--bun", type=Path, required=True)
    parser.add_argument("--pi", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print("MATCHED_BACKEND_RESULT=" + json.dumps(worker(args)), flush=True)
    else:
        if args.output is None:
            parser.error("--output is required for a comparison run")
        run(args)


if __name__ == "__main__":
    main()
