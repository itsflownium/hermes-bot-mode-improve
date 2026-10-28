"""Deterministic loopback fault probes: real agent/tools, scripted model responses.

These cases grade actual local artifacts and honest stops. They measure the
continuation mechanism, not a real model's probability of completing a task.
"""

from __future__ import annotations

import copy
from itertools import pairwise
from pathlib import Path

CASES = (
    "premature_final",
    "already_complete",
    "blocked",
    "cancelled",
    "history_only",
    "budget_exhausted",
)


def run_case(case: str, home: Path, workspace: Path) -> dict:
    from tests.e2e.core.history._helpers import NO_BACKGROUND_REVIEW, OFFLINE_CONFIG
    from tests.fakes.fake_llm_provider import (
        FakeLLMServer,
        Text,
        ToolCall,
        write_hermes_home,
    )
    from run_agent import AIAgent

    workspace.mkdir(parents=True, exist_ok=True)
    report, attachment = workspace / "report.txt", workspace / "attachment.txt"

    def todos(report_status="pending", attachment_status="pending"):
        return ToolCall(
            "tool_call",
            {
                "calls": [
                    {
                        "name": "todo_list",
                        "arguments": {
                            "todos": [
                                {
                                    "id": "report",
                                    "content": "Create report.txt containing REPORT",
                                    "status": report_status,
                                },
                                {
                                    "id": "attachment",
                                    "content": "Create attachment.txt containing ATTACHMENT",
                                    "status": attachment_status,
                                },
                            ]
                        },
                    }
                ]
            },
        )

    write_report = ToolCall("write_file", {"path": str(report), "content": "REPORT"})
    write_attachment = ToolCall(
        "write_file", {"path": str(attachment), "content": "ATTACHMENT"}
    )
    done = Text("All deliverables are done.")
    blocked = Text(
        "Blocked: I need the user to supply the missing input. The deliverables remain unfinished."
    )
    scripts = {
        "premature_final": [
            todos(),
            write_report,
            todos("completed"),
            done,
            write_attachment,
            todos("completed", "completed"),
            done,
        ],
        "already_complete": [
            todos(),
            write_report,
            write_attachment,
            todos("completed", "completed"),
            done,
        ],
        "blocked": [todos(), blocked, blocked],
        "cancelled": [todos("cancelled", "cancelled"), Text("Cancelled as requested.")],
        "history_only": [
            Text("The old checklist remains pending; this is a status reply.")
        ],
        "budget_exhausted": [todos(), done],
    }
    responses = iter(scripts[case])
    resuming = False

    def respond(_request):
        return Text("Status only.") if resuming else next(responses, blocked)

    with FakeLLMServer(respond) as server:
        write_hermes_home(
            home, server.base_url, extra_config=OFFLINE_CONFIG + NO_BACKGROUND_REVIEW
        )
        agent = AIAgent(
            provider="custom",
            base_url=server.base_url,
            api_key="sk-fake",
            model="fake-model",
            enabled_toolsets=["todo", "file"],
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
            skip_background_review=True,
            save_trajectories=False,
            max_iterations=2 if case == "budget_exhausted" else 12,
            cwd=str(workspace),
        )
        if case == "history_only":
            agent._todo_store.write(
                [{"id": "old", "content": "Historical work", "status": "pending"}]
            )
        try:
            result = agent.run_conversation(
                "Create both specified files and keep the checklist current."
                if case not in {"blocked", "cancelled", "history_only"}
                else {
                    "blocked": "Wait for the missing user input and explain the blocker.",
                    "cancelled": "Cancel both deliverables.",
                    "history_only": "Only report the old task status.",
                }[case],
                conversation_history=[],
                task_id=f"probe-{case}",
            )
            artifacts = {
                "report": report.read_text() if report.exists() else None,
                "attachment": attachment.read_text() if attachment.exists() else None,
            }
            requests = copy.deepcopy(server.main_requests())
            first_count = len(requests)
            resume = None
            if case == "premature_final":
                resuming = True
                agent.run_conversation(
                    "Only report the status now.",
                    conversation_history=result["messages"],
                    task_id="probe-resume",
                )
                resume = {
                    "request_count": len(server.main_requests()) - first_count,
                    "written_this_turn": agent._todo_written_this_turn
                    if hasattr(agent, "_todo_written_this_turn")
                    else False,
                }
                requests = copy.deepcopy(server.main_requests())
        finally:
            agent.close()
    artifact_pass = artifacts == {"report": "REPORT", "attachment": "ATTACHMENT"}
    text = result.get("final_response") or ""
    checks = {
        "premature_final": artifact_pass,
        "already_complete": artifact_pass and first_count == 5,
        "blocked": "blocked" in text.lower()
        and first_count <= 3
        and all(value is None for value in artifacts.values()),
        "cancelled": "cancelled" in text.lower() and first_count == 2,
        "history_only": first_count == 1
        and all(value is None for value in artifacts.values()),
        "budget_exhausted": "unfinished" in text.lower()
        and "not been verified" in text.lower()
        and all(value is None for value in artifacts.values()),
    }
    prefix_stable = all(
        previous.get("messages", [])
        == following.get("messages", [])[: len(previous.get("messages", []))]
        for previous, following in pairwise(requests)
    )
    tool_surface_stable = all(
        item.get("tools") == requests[0].get("tools") for item in requests
    )
    return {
        "case": case,
        "pass": checks[case],
        "main_requests": first_count,
        "artifacts": artifacts,
        "final_response": text,
        "checklist": result.get("task_checklist"),
        "prefix_stable": prefix_stable,
        "tool_surface_stable": tool_surface_stable,
        "resume": resume,
        "model": "scripted_loopback_http",
        "paid_model_calls": 0,
    }
