"""A newly authored unfinished checklist gets one bounded completion opportunity."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from agent.inline_tool_executors import InlineToolContext, _RAW_INLINE_TOOL_EXECUTORS
from agent.turn_stop_gates import apply_stop_gates
from tools.todo_tool import TodoStore


def _agent():
    return SimpleNamespace(
        _todo_store=TodoStore(),
        _task_completion_guidance=True,
        _emit_interim_assistant_message=Mock(),
        _flush_messages_to_session_db=Mock(),
        _interim_content_was_streamed=lambda _text: False,
        _turn_file_mutation_paths=set(),
    )


def _stop(agent, messages):
    return apply_stop_gates(
        agent,
        {"role": "assistant", "content": "All done."},
        final_response="All done.",
        messages=messages,
        conversation_history=[],
        pending_verification_response=None,
        pending_verification_response_previewed=False,
    )


def test_new_pending_work_is_named_once_and_completed_work_is_not_repeated(monkeypatch):
    from hermes_cli.config import set_config_value

    set_config_value("agent.todo_completion_nudges", "1")
    agent = _agent()
    execute = _RAW_INLINE_TOOL_EXECUTORS["todo_list"]
    args = {
        "todos": [
            {"id": "report", "content": "Write the report", "status": "completed"},
            {
                "id": "attachment",
                "content": "Create the requested attachment",
                "status": "pending",
            },
        ]
    }
    result = json.loads(execute(agent, args, InlineToolContext("task")))
    assert result["summary"]["pending"] == 1
    messages = [{"role": "user", "content": "Create a report and attachment."}]
    verdict = _stop(agent, messages)
    assert verdict.continue_turn is True
    assert "attachment" in messages[-1]["content"]
    assert "Write the report" not in messages[-1]["content"]
    before = list(messages)
    assert _stop(agent, messages).continue_turn is False
    assert messages == before


def test_history_only_disabled_and_cancelled_checklists_do_not_force_more_work():
    from hermes_cli.config import set_config_value

    agent = _agent()
    agent._todo_store.write([{"id": "old", "content": "Old work", "status": "pending"}])
    assert _stop(agent, []).continue_turn is False
    _RAW_INLINE_TOOL_EXECUTORS["todo_list"](
        agent,
        {"todos": [{"id": "new", "content": "New work", "status": "pending"}]},
        InlineToolContext("task"),
    )
    set_config_value("agent.todo_completion_nudges", "0")
    assert _stop(agent, []).continue_turn is False
    set_config_value("agent.todo_completion_nudges", "1")
    _RAW_INLINE_TOOL_EXECUTORS["todo_list"](
        agent,
        {"todos": [{"id": "new", "content": "New work", "status": "cancelled"}]},
        InlineToolContext("task"),
    )
    assert _stop(agent, []).continue_turn is False
