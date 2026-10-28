"""Real managed Bot Chats can review file deliverables without a todo-list prelude."""

import os
from itertools import pairwise
from pathlib import Path
import uuid

import pytest

from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
from tests.fakes.fake_llm_provider import (
    FakeLLMServer,
    Text,
    ToolCall,
    write_hermes_home,
)


def _run(
    tmp_path,
    files,
    *,
    title="Bot Chat",
    enabled=True,
    max_iterations=10,
    read_only=False,
    second_turn=False,
):
    from hermes_cli.config import set_config_value
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from utils import atomic_json_write

    home = Path(os.environ["HERMES_HOME"])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls = [
        ToolCall("write_file", {"path": str(workspace / name), "content": content})
        for name, content in files
    ]
    script = (
        [Text("Status only.")]
        if read_only
        else [calls[0], Text("All done."), *calls[1:], Text("All done.")]
    )
    with FakeLLMServer(script) as server:
        write_hermes_home(
            home, server.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
        )
        set_config_value("bot_mode.completion_review", "true" if enabled else "false")
        atomic_json_write(
            home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Fixture"}}}
        )
        database = SessionDB(db_path=home / "state.db")
        sid = "bot-review-" + uuid.uuid4().hex
        database.create_session(sid, "desktop")
        database.set_session_title(sid, title)
        agent = AIAgent(
            provider="custom",
            base_url=server.base_url,
            api_key="fixture-local-only",
            model="fake-model",
            enabled_toolsets=["todo", "file"],
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
            skip_background_review=True,
            save_trajectories=False,
            session_db=database,
            session_id=sid,
            platform="desktop",
            max_iterations=max_iterations,
            cwd=str(workspace),
        )
        try:
            prompt = (
                "Only report status. Do not edit any files."
                if read_only
                else "Create every requested file: "
                + ", ".join(name for name, _ in files)
            )
            result = agent.run_conversation(
                prompt, conversation_history=[], task_id=sid
            )
            request_count = len(server.main_requests())
            resumed = None
            if second_turn:
                server.drop_unconsumed()
                server.push(Text("Status only."))
                resumed = agent.run_conversation(
                    "Only report status; do not edit any files.",
                    conversation_history=result["messages"],
                    task_id=sid,
                )
                resumed = {
                    "requests": len(server.main_requests()) - request_count,
                    "review": resumed.get("task_completion_review"),
                }
            observed = {
                name: (workspace / name).read_text()
                if (workspace / name).exists()
                else None
                for name, _ in files
            }
            requests = server.main_requests()
        finally:
            agent.close()
            database.close()
    return result, observed, request_count, requests, resumed


@pytest.mark.parametrize(
    "files",
    [
        [
            ("settings.json", '{"enabled":true}'),
            ("summary.csv", "name,count\nalpha,2\n"),
        ],
        [
            ("notes.md", "# Notes\n"),
            ("audit.tsv", "key\tvalue\nalpha\t2\n"),
            ("receipt.json", '{"ready":true}'),
        ],
    ],
)
def test_missing_requested_outputs_are_created_without_a_checklist(tmp_path, files):
    result, observed, count, requests, resumed = _run(tmp_path, files, second_turn=True)
    assert observed == dict(files), (observed, result)
    assert result["task_completion_review"] == {
        "requested": True,
        "completion_verified": False,
    }
    assert count == len(files) + 2
    assert resumed == {"requests": 1, "review": None}
    assert all(
        left["messages"] == right["messages"][: len(left["messages"])]
        for left, right in pairwise(requests)
    )
    assert all(request["tools"] == requests[0]["tools"] for request in requests)


@pytest.mark.parametrize(
    "settings, expected_count",
    [
        ({"title": "Scratch"}, 2),
        ({"enabled": False}, 2),
        ({"read_only": True}, 1),
        ({"max_iterations": 2}, 2),
    ],
)
def test_review_respects_surface_config_reads_and_the_existing_budget(
    tmp_path, settings, expected_count
):
    result, _observed, count, _requests, _resumed = _run(
        tmp_path, [("note.txt", "ONE")], **settings
    )
    assert count == expected_count
    if settings.get("max_iterations") == 2:
        assert "not been verified" in result["final_response"]
        assert "All done." not in result["final_response"]
    else:
        assert result.get("task_completion_review") is None
