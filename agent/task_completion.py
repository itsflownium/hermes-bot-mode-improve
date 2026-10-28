"""Bounded completion checks for a checklist the agent actually changed this turn."""

from __future__ import annotations


def _remaining(agent) -> list[dict]:
    store = getattr(agent, "_todo_store", None)
    return (
        [
            item
            for item in store.read()
            if item.get("status") in {"pending", "in_progress"}
        ]
        if store is not None
        else []
    )


def completion_nudge(agent) -> str | None:
    if (
        getattr(agent, "_task_completion_guidance", True) is False
        or getattr(agent, "_interrupt_requested", False) is True
    ):
        return None
    if getattr(agent, "_todo_written_this_turn", False) is not True:
        from agent.task_completion_bot_mode import artifact_completion_nudge

        return artifact_completion_nudge(agent)
    from hermes_cli.config import load_config_readonly

    value = (load_config_readonly().get("agent") or {}).get("todo_completion_nudges", 1)
    limit = min(3, max(0, value)) if type(value) is int else 0
    used = getattr(agent, "_todo_completion_nudges", 0)
    remaining = _remaining(agent)
    if not remaining or type(used) is not int or used >= limit:
        return None
    agent._todo_completion_nudges = used + 1
    lines = [
        f"- {item['id']}: {item['content']} ({item['status']})"
        for item in remaining[:20]
    ]
    detail = "\n".join(lines)
    if len(detail) > 2500:
        detail = (
            detail[:2500]
            + "\n[Checklist display truncated; read todo_list for the full list.]"
        )
    return (
        "[System note: The task list you changed this turn still has "
        f"{len(remaining)} unfinished item(s). Check the remaining requested deliverables before finishing. "
        "Continue only within the user's current instructions and permissions. If work is blocked or awaiting "
        "input, explain what remains and why; do not fabricate completion or cancel items merely to clear this check.]\n"
        + detail
    )


def completion_result_fields(agent) -> dict:
    review = (
        {"task_completion_review": {"requested": True, "completion_verified": False}}
        if getattr(agent, "_artifact_completion_reviewed", False) is True
        else {}
    )
    if getattr(agent, "_todo_written_this_turn", False) is not True:
        return review
    remaining = _remaining(agent)
    return {
        **review,
        "task_checklist": {
            "reported_status": "incomplete" if remaining else "no_active_items",
            "remaining_count": len(remaining),
            "remaining_ids": [item["id"] for item in remaining[:20]],
            "completion_verified": False,
        },
    }


def completion_budget_fallback(agent, candidate):
    """Do not republish an unchecked 'done' candidate after its continuation ran out."""
    nudges = getattr(agent, "_todo_completion_nudges", 0)
    if type(nudges) is not int or nudges <= 0:
        if getattr(agent, "_artifact_completion_reviewed", False) is True:
            return (
                "The iteration budget ended before the Bot Mode completion review finished. "
                "Requested deliverables have not been verified. Review the remaining work before continuing."
            )
        return candidate
    remaining = _remaining(agent)
    if not remaining:
        return candidate
    ids = ", ".join(item["id"] for item in remaining[:20])
    return (
        f"The iteration budget ended with {len(remaining)} unfinished checklist item(s): {ids}. "
        "Task completion has not been verified. Review the remaining work before continuing."
    )
