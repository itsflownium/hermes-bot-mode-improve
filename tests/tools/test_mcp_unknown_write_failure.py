"""A side effect followed by a lost reply is unknown, not proof that the write failed."""

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from tools import mcp_tool_handlers as handlers


def _install(monkeypatch, call_tool, *, read_only=False, lock=None):
    handlers._core._reset_server_error("fixture")
    server = SimpleNamespace(
        session=SimpleNamespace(call_tool=call_tool),
        _rpc_lock=lock or asyncio.Lock(),
        _pending_call_context=None,
        _inflight_tasks=set(),
        _reconnecting=False,
        _is_http=lambda: True,
    )
    monkeypatch.setattr(handlers, "_acquire_call_server", lambda *args: (server, None))
    monkeypatch.setattr(handlers, "_tool_is_read_only", lambda *args: read_only)
    monkeypatch.setattr(
        handlers._loop, "_run_on_mcp_loop", lambda call, **kwargs: asyncio.run(call())
    )
    return handlers._make_tool_handler("fixture", "create", 1)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("reply timed out"),
        InterruptedError("new user input"),
        ValueError("invalid reply"),
    ],
)
def test_write_effect_then_failed_reply_is_reported_unknown_without_replay(
    tmp_path, monkeypatch, error
):
    database = tmp_path / "service.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE effects (value TEXT)")
    calls = []

    async def call_tool(name, arguments, **kwargs):
        calls.append((name, arguments))
        with sqlite3.connect(database) as connection:
            connection.execute("INSERT INTO effects VALUES ('committed')")
        raise error

    result = json.loads(_install(monkeypatch, call_tool)({"value": "fixture"}))
    assert result["outcome_uncertain"] is True
    assert result["reconciliation_required"] is True
    assert "verify" in result["error"].lower()
    assert len(calls) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM effects").fetchone() == (1,)


@pytest.mark.parametrize(
    "mode", ["read_only_timeout", "before_dispatch", "application_error", "success"]
)
def test_known_replies_and_undispatched_or_read_only_calls_are_not_unknown(
    monkeypatch, mode
):
    from mcp.types import CallToolResult, TextContent

    calls = []

    async def call_tool(*args, **kwargs):
        calls.append(True)
        if mode == "read_only_timeout":
            raise TimeoutError("read timed out")
        return CallToolResult(
            content=[TextContent(type="text", text="known reply")],
            isError=mode == "application_error",
        )

    @asynccontextmanager
    async def failed_lock():
        raise TimeoutError("lock failed before dispatch")
        yield  # pragma: no cover -- required to define an async context manager

    handler = _install(
        monkeypatch,
        call_tool,
        read_only=mode == "read_only_timeout",
        lock=failed_lock() if mode == "before_dispatch" else None,
    )
    result = json.loads(handler({}))
    assert not result.get("outcome_uncertain"), result
    assert len(calls) == (0 if mode == "before_dispatch" else 1)


def test_authenticated_retry_that_commits_then_loses_reply_is_unknown(
    monkeypatch, tmp_path
):
    from mcp.client.auth import OAuthFlowError
    from tools import mcp_oauth_manager

    database = tmp_path / "authenticated-service.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE effects (value TEXT)")
    attempts = []

    async def call_tool(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            raise OAuthFlowError("expired before dispatch")
        with sqlite3.connect(database) as connection:
            connection.execute("INSERT INTO effects VALUES ('committed')")
        raise TimeoutError("authenticated write reply was lost")

    async def recover(*args):
        return True

    monkeypatch.setattr(
        mcp_oauth_manager, "get_manager", lambda: SimpleNamespace(handle_401=recover)
    )
    result = json.loads(_install(monkeypatch, call_tool)({}))
    assert result["outcome_uncertain"] is True
    assert not result.get("needs_reauth"), result
    assert len(attempts) == 2
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM effects").fetchone() == (1,)
