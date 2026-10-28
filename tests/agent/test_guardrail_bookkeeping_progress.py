"""Task bookkeeping must not give unrelated failed tool calls a fresh retry allowance."""

import json

import pytest

from agent.tool_guardrails import ToolCallGuardrailConfig, ToolCallGuardrailController


@pytest.mark.parametrize("bookkeeping_tool", [
    "todo", "todo_list", "memory", "skill_manage", "send_message", "cronjob", "cronjob_manage",
])
def test_bookkeeping_does_not_reopen_an_exhausted_failed_call(bookkeeping_tool):
    controller = ToolCallGuardrailController(ToolCallGuardrailConfig(
        hard_stop_enabled=True, exact_failure_block_after=2, same_tool_failure_halt_after=99,
    ))
    args = {"resource": "report"}
    for revision in range(2):
        assert controller.before_call("mcp_reports_fetch", args).allows_execution
        controller.after_call("mcp_reports_fetch", args, '{"error":"access denied"}', failed=True)
        controller.after_call(bookkeeping_tool, {"revision": revision},
                              json.dumps({"success": True, "revision": revision}), failed=False)

    decision = controller.before_call("mcp_reports_fetch", args)
    assert decision.code == "repeated_exact_failure_block"
    assert decision.count == 2


@pytest.mark.parametrize("intervening_tool,should_halt", [
    ("todo_list", True), ("memory", True), ("patch", False), ("terminal", False),
])
def test_failure_budget_survives_bookkeeping_but_allows_execution_repairs(intervening_tool, should_halt):
    controller = ToolCallGuardrailController(ToolCallGuardrailConfig(
        hard_stop_enabled=True, same_tool_failure_halt_after=3,
    ))
    for revision in range(2):
        controller.after_call("mcp_reports_fetch", {"resource": str(revision)},
                              '{"error":"access denied"}', failed=True)
        controller.after_call(intervening_tool, {"path": "config.py"},
                              '{"success":true,"exit_code":0}', failed=False)

    decision = controller.after_call("mcp_reports_fetch", {"resource": "last"},
                                     '{"error":"access denied"}', failed=True)
    assert decision.should_halt is should_halt
    if should_halt:
        assert decision.code == "same_tool_failure_halt"


@pytest.mark.parametrize("failed_tool,repair_tool", [
    ("memory", "memory"), ("todo", "todo_list"), ("cronjob", "cronjob_manage"),
    ("skill_view", "skill_manage"), ("send_message", "send_message"),
])
def test_successful_family_repair_reopens_only_its_own_failed_calls(failed_tool, repair_tool):
    controller = ToolCallGuardrailController(ToolCallGuardrailConfig(
        hard_stop_enabled=True, exact_failure_block_after=2, same_tool_failure_halt_after=99,
    ))
    args = {"resource": "original"}
    for _ in range(2):
        controller.after_call(failed_tool, args, '{"error":"capacity exceeded"}', failed=True)
        controller.after_call("mcp_reports_fetch", args, '{"error":"access denied"}', failed=True)
    controller.after_call(repair_tool, {"resource": "repair", "action": "remove"},
                          '{"success":true}', failed=False)

    assert controller.before_call(failed_tool, args).allows_execution
    assert controller.before_call("mcp_reports_fetch", args).code == "repeated_exact_failure_block"

