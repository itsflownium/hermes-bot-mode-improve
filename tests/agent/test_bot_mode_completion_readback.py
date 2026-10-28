"""A completion check must see actual current files, not just earlier write receipts."""

import os
from pathlib import Path

import pytest

from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
from tests.fakes.fake_llm_provider import (
    FakeLLMServer,
    Text,
    ToolCall,
    write_hermes_home,
)


@pytest.mark.parametrize(
    "name,initial,current",
    [
        ("settings.json", '{"value":"BEFORE_EDIT"}', '{"value":"AFTER_EDIT"}'),
        (
            "table.tsv",
            "key\tvalue\nitem\tBEFORE_EDIT\n",
            "key\tvalue\nitem\tAFTER_EDIT\n",
        ),
    ],
)
def test_review_uses_current_file_evidence_after_an_external_edit(
    tmp_path, name, initial, current
):
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from utils import atomic_json_write

    home = Path(os.environ["HERMES_HOME"])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source, receipt = workspace / name, workspace / "observed.txt"
    step = 0

    def respond(record):
        nonlocal step
        step += 1
        if step == 1:
            return ToolCall("write_file", {"path": str(source), "content": initial})
        if step == 2:
            source.write_text(current)
            return Text("All done.")
        if step == 3:
            latest = record["body"]["messages"][-1].get("content", "")
            if "AFTER_EDIT" in str(latest):
                return ToolCall(
                    "write_file", {"path": str(receipt), "content": "AFTER_EDIT"}
                )
        return Text("Finished reviewing the available evidence.")

    with FakeLLMServer(respond) as server:
        write_hermes_home(
            home, server.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
        )
        atomic_json_write(
            home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Fixture"}}}
        )
        database = SessionDB(db_path=home / "state.db")
        database.create_session("readback", "desktop")
        database.set_session_title("readback", "Bot Chat")
        agent = AIAgent(
            provider="custom",
            base_url=server.base_url,
            api_key="fixture-local-only",
            model="fake-model",
            enabled_toolsets=["file"],
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
            skip_background_review=True,
            save_trajectories=False,
            session_db=database,
            session_id="readback",
            platform="desktop",
            max_iterations=8,
            cwd=str(workspace),
        )
        try:
            agent.run_conversation(
                "Create the requested file and record its current value after reviewing the actual saved file.",
                conversation_history=[],
                task_id="readback",
            )
        finally:
            agent.close()
            database.close()
    assert receipt.exists(), (
        "the reviewer never received the changed file's current value"
    )
    assert receipt.read_text() == "AFTER_EDIT"


def test_shortened_review_does_not_authorize_an_unread_whole_file_overwrite(tmp_path):
    import json
    from tools.file_tools import read_file_tool, write_file_tool

    path = tmp_path / "long.txt"
    original = "important existing content\n" * 200
    path.write_text(original)
    task = "review-only"
    read_file_tool(str(path), task_id=task, _completion_preview=True)
    refused = json.loads(write_file_tool(str(path), "replacement", task_id=task))
    assert refused.get("error"), refused
    assert path.read_text() == original
    read_file_tool(str(path), task_id=task)
    replaced = json.loads(write_file_tool(str(path), "replacement", task_id=task))
    assert not replaced.get("error"), replaced
    assert path.read_text() == "replacement"
