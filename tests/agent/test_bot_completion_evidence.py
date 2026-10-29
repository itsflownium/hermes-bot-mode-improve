"""A bounded Bot Chat review must see omitted outputs and the end of a document."""

import json
import os
from itertools import pairwise
from pathlib import Path

import pytest

from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
from tests.fakes.fake_llm_provider import FakeLLMServer, Text, ToolCall, write_hermes_home


@pytest.mark.parametrize("scenario", ["document_tail", "fourth_output", "completed_checklist"])
def test_review_can_repair_current_evidence_even_after_checklist_completion(tmp_path, scenario):
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from utils import atomic_json_write

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "z-report.md"
    prefix = "Background detail.\n" * 180 if scenario == "document_tail" else ""
    files = [(target, prefix + "Status: ORIGINAL\n")]
    if scenario == "fourth_output":
        files = [(workspace / f"part-{i}.json", '{"ok":true}') for i in range(3)] + files
    step = 0

    def respond(record):
        nonlocal step
        step += 1
        if scenario == "completed_checklist" and step == 1:
            return ToolCall("todo_list", {"todos": [{"id": "report", "content": "Write and review report", "status": "completed"}]})
        current = step - (scenario == "completed_checklist")
        if current == 1:
            calls = [("write_file", {"path": str(p), "content": content}) for p, content in files]
            return ToolCall(*calls[0], parallel=calls[1:])
        if current == 2:
            target.write_text(prefix + "Status: NEEDS_REPAIR\n", encoding="utf-8")
            return Text("All requested outputs are correct.")
        if current == 3 and "NEEDS_REPAIR" in str(record["body"]["messages"][-1]["content"]):
            return ToolCall("read_file", {"path": str(target)})
        if current == 4:
            return ToolCall("write_file", {"path": str(target), "content": "Status: REVIEWED\n"})
        return Text("The report has been reviewed against current saved contents.")

    home = Path(os.environ["HERMES_HOME"])
    with FakeLLMServer(respond) as server:
        write_hermes_home(home, server.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW)
        from hermes_cli.config import set_config_value
        set_config_value("tools.tool_search.enabled", "off")
        atomic_json_write(home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Review"}}})
        db = SessionDB(db_path=home / "state.db")
        db.create_session("evidence-review", "desktop")
        db.set_session_title("evidence-review", "Bot Chat")
        agent = AIAgent(
            provider="custom", base_url=server.base_url, api_key="fixture-local-only", model="fake-model",
            enabled_toolsets=["file", "todo"], quiet_mode=True, skip_memory=True, skip_context_files=True,
            skip_background_review=True, save_trajectories=False, session_db=db, session_id="evidence-review",
            platform="desktop", max_iterations=9, cwd=str(workspace),
        )
        try:
            result = agent.run_conversation("Create the reports and verify their current saved contents before finishing.",
                                            conversation_history=[], task_id="evidence-review")
            requests = server.main_requests()
            if scenario == "completed_checklist":
                assert agent._todo_store.read(), result["messages"]
                assert result["task_checklist"]["reported_status"] == "no_active_items"
            assert target.read_text() == "Status: REVIEWED\n", result
            assert result["task_completion_review"]["completion_verified"] is False
            assert len(requests) == 5 + (scenario == "completed_checklist")
            assert all(a["messages"] == b["messages"][:len(a["messages"])] for a, b in pairwise(requests))
            assert all(r["tools"] == requests[0]["tools"] for r in requests)
            server.drop_unconsumed()
            server.push(Text("Status only."))
            before = len(server.main_requests())
            resumed = agent.run_conversation("Only report status; make no edits.",
                                             conversation_history=result["messages"], task_id="evidence-review")
            assert len(server.main_requests()) == before + 1
            assert resumed.get("task_completion_review") is None
        finally:
            agent.close()
            db.close()


def test_review_excerpts_are_bounded_and_do_not_hide_omitted_files(tmp_path):
    from types import SimpleNamespace
    from agent.task_completion_readback import completion_readback

    paths = []
    for i in range(9):
        path = tmp_path / f"document-{i}.txt"
        path.write_text("A" * 5000 + "\nEND\n", encoding="utf-8")
        paths.append(str(path))
    agent = SimpleNamespace(_current_task_id="bounded-review", _turn_file_mutation_paths=set(paths))
    preview = completion_readback(agent)
    data = json.loads(preview.split("\n", 1)[1])
    assert len(preview) < 10_000
    assert data["files_changed"] == 9
    assert data["files_omitted"] == data["files_changed"] - data["files_shown"]
    assert data["files_omitted"] > 0
    assert all(item["readback"].get("review_excerpt_truncated") for item in data["excerpts"])
