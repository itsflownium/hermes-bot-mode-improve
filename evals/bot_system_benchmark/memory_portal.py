"""Small real-agent memory smoke test through the explicitly requested Nous route."""

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time


def run(request):
    sys.path.insert(0, request["repository"])
    from hermes_cli.auth_nous import resolve_nous_runtime_credentials

    credentials = resolve_nous_runtime_credentials(timeout_seconds=15)
    with tempfile.TemporaryDirectory(prefix="portal-memory-") as directory:
        root = Path(directory)
        home = root / "profile"
        workspace = root / "workspace"
        home.mkdir()
        workspace.mkdir()
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HERMES_RUNTIME_DIR"] = str(root / "runtime")
        os.chdir(workspace)
        from hermes_cli.config import atomic_config_write, get_config_path

        atomic_config_write(
            get_config_path(),
            {"fallback_providers": [], "memory": {"user_profile_enabled": False}},
        )
        memory = home / "memories" / "MEMORY.md"
        memory.parent.mkdir()
        memory.write_text("Preferred reminder interval: 17 minutes.\n")
        from run_agent import AIAgent

        agent = AIAgent(
            model="deepseek/deepseek-v4.1-flash",
            provider="nous",
            api_key=credentials["api_key"],
            base_url=credentials["base_url"],
            api_mode="chat_completions",
            enabled_toolsets=[],
            quiet_mode=True,
            skip_context_files=True,
            skip_background_review=True,
            max_iterations=2,
            max_tokens=1024,
            reasoning_config={"enabled": False},
            run_budget_seconds=35,
            request_overrides={"timeout": 30},
            fallback_model={},
            cwd=str(workspace),
        )
        agent.client.max_retries = 0
        assert agent._memory_store is not None
        # Use the store's real profile-bound path rather than assuming a state layout.
        actual_memory = agent._memory_store._path_for("memory")
        assert actual_memory == memory, (actual_memory, memory)
        frozen = copy.deepcopy(agent._memory_store._system_prompt_snapshot)
        assert "17 minutes" in frozen["memory"]
        observations = []
        build = agent._build_api_kwargs

        def capture(*args, **kwargs):
            if len(observations) >= 6:
                raise RuntimeError("Smoke-test request budget exhausted")
            wire = build(*args, **kwargs)
            messages = wire.get("messages", [])
            prefix = [
                row for row in messages if row.get("role") in ("system", "developer")
            ]
            observations.append(
                {
                    "model": wire.get("model"),
                    "prefix_sha256": hashlib.sha256(
                        json.dumps(prefix, sort_keys=True).encode()
                    ).hexdigest(),
                    "has_native_memory_note": any(
                        "Native memory state changed; revision="
                        in str(row.get("content", ""))
                        for row in messages
                        if row.get("role") == "user"
                    ),
                    "tool_schema_count": len(wire.get("tools") or []),
                }
            )
            return wire

        agent._build_api_kwargs = capture
        history = []
        rows = []
        output = Path(request["output"])
        receipt = {
            "scope": "One three-turn memory conversation per revision; not an independent benchmark or an OpenBot model comparison.",
            "provider": "nous",
            "model": "deepseek/deepseek-v4.1-flash",
            "inference_cost_usd": None,
            "billing_note": "Uses the requested existing Nous Portal account. No separate DeepSeek/OpenRouter key is used; dollar cost is not supplied by this smoke receipt.",
            "max_output_tokens_per_request": 1024,
            "max_request_builds": 6,
            "planned": request["cases"],
            "turns": rows,
            "wire_observations": observations,
        }
        with output.open("x") as handle:
            json.dump(receipt, handle, indent=2)
        try:
            for index, case in enumerate(request["cases"]):
                if case["state"] is None:
                    memory.unlink(missing_ok=True)
                else:
                    memory.write_text(case["state"])
                row = {
                    "case": case["id"],
                    "expected": case["expected"],
                    "status": "admitted",
                }
                rows.append(row)
                output.write_text(json.dumps(receipt, indent=2))
                previous = copy.deepcopy(history)
                start = time.perf_counter()
                result = agent.run_conversation(
                    "Based only on CURRENT native memory, what is my preferred reminder interval in minutes? "
                    "Reply with just the integer, or UNKNOWN if the current native memory has no such entry.",
                    conversation_history=history,
                )
                history = result.get("messages", [])
                answer = str(result.get("final_response") or "").strip()
                row.update(
                    status="completed",
                    answer=answer,
                    passed=answer == case["expected"],
                    elapsed_ms=(time.perf_counter() - start) * 1000,
                    past_messages_unchanged=history[: len(previous)] == previous,
                    frozen_memory_unchanged=agent._memory_store._system_prompt_snapshot
                    == frozen,
                )
                output.write_text(json.dumps(receipt, indent=2))
                print(json.dumps(row), flush=True)
                if result.get("completed") is False:
                    break
        finally:
            agent.close()
            output.write_text(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    run(json.load(sys.stdin))
