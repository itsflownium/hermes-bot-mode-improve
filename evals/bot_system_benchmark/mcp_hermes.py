"""Read-only live MCP handshake and discovery through Hermes production code."""

import asyncio
import json
import logging
import sys
import time

request = json.load(sys.stdin)
sys.path.insert(0, request["repository"])
from tools import mcp_tool
from tools.mcp_tool_discovery import _connect_server


async def main():
    mcp_tool._ensure_mcp_sdk()
    server = None
    started = time.perf_counter()
    outcome = {"phase": "connect_and_discover", "tool_names": [], "tool_count": 0}
    try:
        server = await asyncio.wait_for(
            _connect_server(
                "public-network-check",
                {
                    "url": request["url"],
                    "connect_timeout": request["timeout_seconds"],
                    "sampling": {"enabled": False},
                    "elicitation": {"enabled": False},
                },
            ),
            timeout=request["timeout_seconds"],
        )
        names = [str(getattr(tool, "name", "")) for tool in server._tools]
        outcome.update(tool_names=names, tool_count=len(names), error=None)
    except Exception as exc:
        logging.getLogger(__name__).exception("MCP connection probe failed")
        outcome["error"] = {"class": type(exc).__name__, "message": str(exc)[:1000]}
    finally:
        if server is not None:
            await server.shutdown()
    outcome["elapsed_ms"] = (time.perf_counter() - started) * 1000
    print(json.dumps(outcome))


asyncio.run(main())
