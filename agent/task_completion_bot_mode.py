"""One completion review for Bot Chat file or completed terminal work."""

from __future__ import annotations


def artifact_completion_nudge(agent) -> str | None:
    if getattr(agent, "_artifact_completion_reviewed", False) is True or not (
        getattr(agent, "_turn_file_mutation_paths", None)
        or getattr(agent, "_turn_terminal_completed", False) is True
    ):
        return None
    from tools.bot_mode_dm import message_agent_authorized

    if not message_agent_authorized(agent):
        return None
    from hermes_cli.config import load_config_readonly

    if (load_config_readonly().get("bot_mode") or {}).get(
        "completion_review", True
    ) is not True:
        return None
    agent._artifact_completion_reviewed = True
    from agent.task_completion_readback import completion_readback

    return (
        (
            "[System note: Before finishing this Bot Chat task, review the original user's request against "
            "the actual tool results and outputs you created. Check every requested deliverable, including "
            "supporting files and delivery steps; a successful edit alone does not prove the entire task is complete. "
            "Compare the saved contents with the requested structure and values, rather than treating a "
            "successful write or valid syntax as proof of correctness. Check that unrelated values were preserved. "
            "A successful process exit also does not prove that requested output files exist or contain "
            "the required results. Inspect outputs created by shell commands when needed. "
            "Use focused reads or relevant checks when the evidence is insufficient. "
            "If something requested is missing or wrong, finish it within the existing permissions and iteration budget. "
            "If blocked, explain the blocker and what remains. Do not invent verification, create unnecessary work, "
            "or repeat external actions whose outcomes are unknown. If everything is already satisfied, give the "
            "final answer now. This is the only completion review reminder for this turn.]"
        )
        + "\n"
        + completion_readback(agent)
    )


def note_terminal_completion(agent, tool_name: str, result, *, task_id=None) -> None:
    """Only an owned, completed command can enable this turn's bounded review."""
    if tool_name != "terminal" or task_id != getattr(agent, "_current_task_id", None):
        return
    if not task_id or getattr(agent, "_turn_failed_file_mutations", None) is None:
        return
    import json

    try:
        data = json.loads(result) if isinstance(result, str) else result
    except (TypeError, ValueError):
        return
    if isinstance(data, dict) and type(data.get("exit_code")) is int:
        agent._turn_terminal_completed = True
