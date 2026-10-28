"""Bounded MCP result envelopes for the existing plugin call boundary."""

import json
from typing import Any


def _preview(text: str, max_chars: int) -> str:
    return text[:max_chars] + "… [truncated]" if len(text) > max_chars else text


def mcp_result_envelope(raw: Any, *, max_chars: int) -> dict[str, Any]:
    """Keep normalized MCP details and failure classification within the plugin's result cap.

    Parse before producing a lossy preview: truncating JSON first would erase an error's
    classification and report a failed operation as successful. Oversized successes retain
    the established raw-text preview; oversized errors keep a bounded error message.
    """
    if not isinstance(raw, str):
        raw = "" if raw is None else str(raw)
    truncated = len(raw) > max_chars
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and "error" in parsed:
        error = _preview(str(parsed["error"]), max_chars) if truncated else parsed["error"]
        envelope = {"ok": False, "error": error}
    elif truncated:
        envelope = {"ok": True, "result": _preview(raw, max_chars)}
    elif isinstance(parsed, dict) and "result" in parsed:
        envelope = {"ok": True, "result": parsed["result"]}
    else:
        envelope = {"ok": True, "result": parsed if parsed is not None else raw}
    if not truncated and isinstance(parsed, dict) and ("error" in parsed or "result" in parsed):
        for key in ("structuredContent", "_meta", "structuredContentTruncated"):
            if key in parsed:
                envelope[key] = parsed[key]
    if truncated:
        envelope["truncated"] = True
    return envelope
