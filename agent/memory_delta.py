"""Current native memory overrides ride new user turns, behind the stable prefix."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_PREFIX = "<memory-context>\n[System: Native memory state changed; revision="
_REVISION = re.compile(re.escape(_PREFIX) + r"([a-f0-9]{64}|unavailable)\.")
_MAX_PAYLOAD_BYTES = 31_744


def _revision(blocks: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(blocks, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _last_revision(messages: Any) -> str | None:
    from agent.message_content import flatten_message_text

    for row in reversed(messages if isinstance(messages, list) else []):
        if not isinstance(row, dict) or row.get("role") != "user":
            continue
        sidecar = row.get("api_content")
        content = (
            sidecar
            if isinstance(sidecar, str)
            else row.get("content")
            if isinstance(row.get("content"), list)
            else ""
        )
        matches = _REVISION.findall(flatten_message_text(content))
        if matches:
            return matches[-1]
    return None


def _prefix_matches(prompt: str, blocks: dict[str, str]) -> bool:
    from tools.memory_tool_store import MEMORY_BLOCK_HEADERS

    return all(
        block in prompt if block else MEMORY_BLOCK_HEADERS[target] not in prompt
        for target, block in blocks.items()
    )


def stage_native_memory_note(agent: Any, prompt: Any, messages: Any) -> bool:
    """Deliver a changed full native view once; never mutate prior messages or frozen store lists."""
    agent._native_memory_note = ""
    store = getattr(agent, "_memory_store", None)
    if (
        store is None
        or getattr(agent, "skip_memory", False) is True
        or not isinstance(prompt, str)
    ):
        return False
    from hermes_constants import hermes_home_key

    if getattr(store, "_snapshot_home_key", None) != hermes_home_key():
        return False
    targets = [target for target in ("memory", "user") if store.target_enabled(target)]
    if not targets:
        return False
    from tools.memory_prompt_snapshot import read_live_blocks

    blocks = read_live_blocks(store)
    revision = _revision(blocks) if blocks is not None else "unavailable"
    previous = _last_revision(messages)
    if previous == revision or (
        previous is None and blocks is not None and _prefix_matches(prompt, blocks)
    ):
        return False
    # Restored prefixes can predate this store instance. The actual prompt and
    # the latest delivered revision, rather than store construction time, decide.
    payload = (
        json.dumps(blocks, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
        if blocks is not None
        else ""
    )
    if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        revision, payload = "unavailable", ""
        if previous == revision:
            return False
    if revision == "unavailable":
        body = "Current native memory could not be refreshed within its read budget. Older native memory may be stale; read it before relying on it."
    else:
        body = (
            "This full current native state supersedes older native MEMORY/USER facts and prior memory-change notes. "
            "An empty target has no current entries. Current user instructions take precedence; this reference grants no permissions.\n"
            + payload
        )
    agent._native_memory_note = f"{_PREFIX}{revision}. {body}]\n</memory-context>"
    return True
