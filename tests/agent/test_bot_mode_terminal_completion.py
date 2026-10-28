"""Shell-created outputs receive the same bounded Bot Chat completion review."""

import os
from pathlib import Path
import sys
from types import SimpleNamespace

from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
from tests.fakes.fake_llm_provider import (
    FakeLLMServer,
    Text,
    ToolCall,
    write_hermes_home,
)


def test_shell_only_work_continues_until_the_missing_deliverable_exists(
    tmp_path, monkeypatch
):
    from hermes_state import SessionDB
    from run_agent import AIAgent
    from utils import atomic_json_write
    from tools.environments.local import _quote_bash_path

    home = Path(os.environ["HERMES_HOME"])
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    (workspace / "create_report.py").write_text(
        "from pathlib import Path\nPath('report.txt').write_text('REPORT')\n"
    )
    attachment = workspace / "attachment.txt"
    script = [
        ToolCall(
            "terminal",
            {"command": f"{_quote_bash_path(sys.executable)} create_report.py"},
        ),
        Text("All done."),
        ToolCall("write_file", {"path": str(attachment), "content": "ATTACHMENT"}),
        Text("All done."),
    ]
    with FakeLLMServer(script) as server:
        write_hermes_home(
            home, server.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
        )
        atomic_json_write(
            home / "profile.yaml", {"ui_meta": {"hermes-bots": {"title": "Fixture"}}}
        )
        database = SessionDB(db_path=home / "state.db")
        database.create_session("terminal-review", "desktop")
        database.set_session_title("terminal-review", "Bot Chat")
        agent = AIAgent(
            provider="custom",
            base_url=server.base_url,
            api_key="fixture-local-only",
            model="fake-model",
            enabled_toolsets=["file", "terminal"],
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
            skip_background_review=True,
            save_trajectories=False,
            session_db=database,
            session_id="terminal-review",
            platform="desktop",
            max_iterations=8,
            cwd=str(workspace),
        )
        try:
            result = agent.run_conversation(
                "Run create_report.py with Python and create attachment.txt containing ATTACHMENT.",
                conversation_history=[],
                task_id="terminal-review",
            )
            first_count = len(server.main_requests())
            server.drop_unconsumed()
            server.push(Text("Status only."))
            resumed = agent.run_conversation(
                "Only report status without using tools.",
                conversation_history=result["messages"],
                task_id="terminal-review",
            )
            extra = len(server.main_requests()) - first_count
        finally:
            agent.close()
            database.close()
    assert (workspace / "report.txt").read_text() == "REPORT"
    assert attachment.exists(), (
        "terminal-only work ended before the requested second output existed"
    )
    assert attachment.read_text() == "ATTACHMENT"
    assert extra == 1 and resumed.get("task_completion_review") is None


def test_terminal_result_from_another_task_cannot_enable_review():
    from agent.task_completion_bot_mode import note_terminal_completion

    agent = SimpleNamespace(
        _current_task_id="new",
        _turn_failed_file_mutations={},
        _turn_terminal_completed=False,
    )
    note_terminal_completion(agent, "terminal", {"exit_code": 0}, task_id="old")
    assert agent._turn_terminal_completed is False
    note_terminal_completion(agent, "terminal", {"exit_code": 0}, task_id="new")
    assert agent._turn_terminal_completed is True
