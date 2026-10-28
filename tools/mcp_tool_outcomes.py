"""Honest write outcomes when the RPC began but its reply could not be accepted."""

from __future__ import annotations

from dataclasses import dataclass
import json

from tools.registry import tool_error


@dataclass
class CallOutcome:
    started: bool = False
    accepted_reply: bool = False

    def uncertain_failure(
        self, server: str, tool: str, *, read_only: bool, result: str
    ) -> str | None:
        if read_only or not self.started or self.accepted_reply:
            return None
        try:
            payload = json.loads(result)
        except (ValueError, TypeError):
            payload = None
        if isinstance(payload, dict) and payload.get("outcome_uncertain") is True:
            payload["reconciliation_required"] = True
            return json.dumps(payload)
        detail = payload.get("error") if isinstance(payload, dict) else None
        diagnostic = (
            f" Reported failure: {detail[:2000]}" if isinstance(detail, str) else ""
        )
        return tool_error(
            f"MCP write-capable tool '{tool}' on '{server}' may have begun execution but no usable reply was confirmed. "
            "Its outcome is UNKNOWN: the operation may already have taken effect. Do not automatically repeat "
            "the write. Verify the external state with a read-only operation or ask the user before re-invoking it."
            + diagnostic,
            outcome_uncertain=True,
            reconciliation_required=True,
            server=server,
            tool=tool,
        )
