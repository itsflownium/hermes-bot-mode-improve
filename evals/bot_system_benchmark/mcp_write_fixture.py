"""Owned local JSON-RPC fault fixture; commits once, then can send an invalid reply."""

import json
import sqlite3
import sys


def _initialize(request):
    return {
        "protocolVersion": request["params"]["protocolVersion"],
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "owned-write-fixture", "version": "1"},
    }


def _list_tools(_request):
    return {
        "tools": [
            {
                "name": "create",
                "description": "Insert a local fixture row",
                "inputSchema": {
                    "type": "object",
                    "properties": {"mode": {"type": "string"}},
                },
                "annotations": {"readOnlyHint": False},
            }
        ]
    }


def _call_tool(request, database):
    mode = request["params"]["arguments"]["mode"]
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO effects VALUES (?)", (mode,))
    return (
        {"content": "malformed after commit"}
        if mode == "invalid_reply"
        else {
            "content": [{"type": "text", "text": "committed"}],
            "isError": False,
        }
    )


def main():
    database = sys.argv[1]
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS effects (mode TEXT)")
    handlers = {
        "initialize": _initialize,
        "tools/list": _list_tools,
        "tools/call": lambda request: _call_tool(request, database),
        "ping": lambda _request: {},
    }
    for line in sys.stdin:
        request = json.loads(line)
        if "id" not in request:
            continue
        handler = handlers.get(request.get("method"))
        result = (
            handler(request)
            if handler is not None
            else {"resources": [], "resourceTemplates": [], "prompts": []}
        )
        print(
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
            flush=True,
        )


if __name__ == "__main__":
    main()
