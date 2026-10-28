"""Read-only bounded native memory views using the same prompt sanitization."""

from __future__ import annotations

import logging

logger = logging.getLogger("tools.memory_tool")
_MAX_FILE_BYTES = 65_536


def sanitize_entry(entry: str, filename: str, target: str) -> str:
    from tools.threat_patterns import scan_for_threats

    findings = (
        scan_for_threats(entry, scope="strict")
        if entry and not entry.startswith("[BLOCKED:")
        else None
    )
    if not findings:
        return entry
    logger.warning(
        "Memory entry from %s blocked at load time: %s", filename, ", ".join(findings)
    )
    return (
        f"[BLOCKED: {filename} entry contained threat pattern(s): {', '.join(findings)}. "
        f"Removed from system prompt; use memory(action=remove, target='{target}') "
        "to delete the original.]"
    )


def read_live_blocks(store) -> dict[str, str] | None:
    """None means unreadable/over-budget; an empty target means a verified empty file."""
    paths = getattr(store, "_snapshot_paths", {})
    blocks = {}
    for target in ("memory", "user"):
        if not store.target_enabled(target):
            continue
        path = paths.get(target)
        if path is None:
            return None
        try:
            with path.open("rb") as handle:
                raw = handle.read(_MAX_FILE_BYTES + 1)
            if len(raw) > _MAX_FILE_BYTES:
                return None
            text = raw.decode("utf-8-sig")
        except FileNotFoundError:
            text = ""
        except (OSError, UnicodeError):
            return None
        entries = list(dict.fromkeys(store._parse_entries(text)))
        safe = [sanitize_entry(entry, path.name, target) for entry in entries]
        blocks[target] = store._render_block(target, safe)
    return blocks
