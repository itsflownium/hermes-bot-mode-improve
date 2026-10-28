"""Real stdio child + MCP SDK + production handler, with a local SQLite effect oracle."""

import json
from pathlib import Path
import sqlite3
import sys


def run_case(mode: str, workspace: Path) -> dict:
    from tools import mcp_tool as core
    from tools import mcp_tool_loop as loop
    from tools.mcp_tool_discovery import _connect_server
    from tools.mcp_tool_handlers import _make_tool_handler
    from tools.mcp_tool_scope import _server_key

    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "effects.db"
    name = "owned-write-fixture"
    key = _server_key(name)
    core._ensure_mcp_sdk()
    loop._ensure_mcp_loop()
    server = loop._run_on_mcp_loop(
        lambda: _connect_server(
            name,
            {
                "command": sys.executable,
                "args": [
                    str(Path(__file__).with_name("mcp_write_fixture.py")),
                    str(database),
                ],
                "connect_timeout": 10,
                "sampling": {"enabled": False},
                "elicitation": {"enabled": False},
            },
        ),
        timeout=15,
    )
    core._servers[key] = server
    try:
        reply = json.loads(_make_tool_handler(name, "create", 5)({"mode": mode}))
        with sqlite3.connect(database) as connection:
            effects = connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0]
    finally:
        core._servers.pop(key, None)
        loop._run_on_mcp_loop(server.shutdown, timeout=10)
        core._reset_server_error(key)
    return {
        "case": mode,
        "effect_count": effects,
        "automatic_replay": effects > 1,
        "reply": reply,
        "pass": effects == 1
        and (
            reply.get("outcome_uncertain") is True
            and reply.get("reconciliation_required") is True
            if mode == "invalid_reply"
            else "error" not in reply and not reply.get("outcome_uncertain")
        ),
        "transport": "real_stdio_mcp_sdk",
        "paid_model_calls": 0,
    }
