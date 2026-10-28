"""Validate live MCP observations before interpreting a positive or rejection case."""

from __future__ import annotations

import json
import math


def _valid_observation(result: dict) -> bool:
    count, names, elapsed = (
        result.get(key) for key in ("tool_count", "tool_names", "elapsed_ms")
    )
    error = result.get("error")
    return (
        "error" in result
        and type(count) is int
        and count >= 0
        and isinstance(names, list)
        and all(isinstance(name, str) and name for name in names)
        and len(set(names)) == len(names)
        and len(names) <= count
        and type(elapsed) in (int, float)
        and (type(elapsed) is int or math.isfinite(elapsed))
        and elapsed >= 0
        and (error is None or isinstance(error, (str, dict)) and bool(error))
    )


def classify(returncode: int, stdout: str, expected: str) -> dict:
    if expected not in {"catalog", "reject"}:
        raise ValueError("unknown MCP case contract")
    if returncode != 0:
        return {"status": "process_error", "contract_pass": False}
    try:
        result = json.loads(stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"status": "malformed_output", "contract_pass": False}
    if not isinstance(result, dict):
        return {"status": "malformed_output", "contract_pass": False}
    if not _valid_observation(result):
        return {"status": "malformed_output", "contract_pass": False, "result": result}
    count, names, error = (
        result.get(key) for key in ("tool_count", "tool_names", "error")
    )
    accepted = error is None and count > 0 and bool(names)
    rejected = error is not None and count == 0 and not names
    passed = accepted if expected == "catalog" else rejected
    return {
        "status": "completed",
        "contract_pass": passed,
        "observed_outcome": "accepted"
        if accepted
        else "rejected"
        if rejected
        else "inconclusive",
        "result": result,
    }
