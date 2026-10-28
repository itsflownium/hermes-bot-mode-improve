"""MCP's JSON-valued structured output survives the registry result boundary."""

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import ClientSession
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from tools import mcp_schema_cache, mcp_tool, mcp_tool_content, mcp_tool_handlers
from tools import mcp_tool_registration
from tools.registry import ToolRegistry


@pytest.fixture
def call_result(monkeypatch, tmp_path):
    """Exercise real SDK output validation, then direct/live/lazy Hermes handlers."""
    for attr in ("_servers", "_lazy_server_configs", "_lazy_server_tool_names", "_lazy_server_fingerprints",
                 "_mcp_tool_server_names", "_server_trust_levels", "_tool_read_only_hints",
                 "_server_error_counts", "_server_breaker_opened_at", "_server_errors_all_application",
                 "_server_tool_scopes", "_server_cost_policies"):
        monkeypatch.setattr(mcp_tool, attr, {})
    monkeypatch.setattr(mcp_schema_cache, "_cache_path", lambda: tmp_path / "schema-cache.json")
    tool = Tool(name="typed", inputSchema={"type": "object"},
                outputSchema={"type": ["object", "array", "string", "number", "boolean", "null"]})
    server = mcp_tool.MCPServerTask("contract")
    server._tools = [tool]
    server.initialize_result = SimpleNamespace(capabilities=SimpleNamespace(resources=None, prompts=None))
    server.session = ClientSession(MagicMock(), MagicMock())
    mcp_tool._servers["contract"] = server
    result = None

    async def rpc(request, *args, **kwargs):
        if request.method == "tools/list":
            return ListToolsResult(tools=[tool])
        return result

    server.session.send_request = AsyncMock(side_effect=rpc)

    def run(factory, timeout=30):
        async def invoke():
            server._rpc_lock = asyncio.Lock()
            return await factory()
        return asyncio.run(invoke())

    monkeypatch.setattr("tools.mcp_tool_loop._run_on_mcp_loop", run)

    def call(value, route="direct", *, declared_output=True):
        nonlocal result
        result = value
        if not declared_output:
            tool.output_schema = None
        if route == "direct":
            return mcp_tool_handlers._make_tool_handler("contract", "typed", 30)({})
        registry = ToolRegistry()
        monkeypatch.setattr("tools.registry.registry", registry)
        if route == "lazy":
            entry = {"tools": [{"name": "typed", "inputSchema": {"type": "object"}}]}
            mcp_tool_registration._register_from_cache_sync("contract", {}, entry)
        else:
            mcp_tool_registration._register_server_tools("contract", server, {})
        return registry.dispatch("mcp__contract__typed", {})

    return call


@pytest.mark.parametrize("route", ["direct", "live", "lazy"])
@pytest.mark.parametrize("value", [{"id": 7}, [1, "two"], "document-id", "", 0, 1.25, False, None])
def test_json_values_keep_their_type_and_presence(call_result, route, value):
    structured_only = CallToolResult.model_validate({"content": [], "structuredContent": value})
    data = json.loads(call_result(structured_only, route))
    assert data == {"result": value}
    assert type(data["result"]) is type(value)
    with_text = CallToolResult.model_validate({
        "content": [{"type": "text", "text": "finished"}], "structuredContent": value})
    data = json.loads(call_result(with_text, route))
    assert data == {"result": "finished", "structuredContent": value}
    assert type(data["structuredContent"]) is type(value)
    dual_emit = with_text.model_copy(update={"content": [TextContent(type="text", text=json.dumps(value))]})
    expected = {"result": json.dumps(value)}
    if not isinstance(value, (dict, list)):
        expected["structuredContent"] = value
    assert json.loads(call_result(dual_emit, route)) == expected
    omitted = CallToolResult.model_validate({"content": [{"type": "text", "text": "finished"}]})
    # An omitted output still fails the SDK's declared output contract, rather than becoming JSON null.
    assert "did not return structured content" in json.loads(call_result(omitted, route))["error"]


def test_omitted_output_is_distinct_from_explicit_null_without_a_schema(call_result):
    omitted = CallToolResult.model_validate({"content": [{"type": "text", "text": "finished"}]})
    assert json.loads(call_result(omitted, declared_output=False)) == {"result": "finished"}
    explicit_null = CallToolResult.model_validate({
        "content": [{"type": "text", "text": "finished"}], "structuredContent": None})
    assert json.loads(call_result(explicit_null, declared_output=False)) == {
        "result": "finished", "structuredContent": None}


@pytest.mark.parametrize("value", [{"existing_id": "row-7"}, ["row-7"], "row-7", 7, 1.25, False, None])
def test_error_output_keeps_structured_details_and_vendor_metadata(call_result, value):
    result = CallToolResult.model_validate({
        "isError": True,
        "content": [{"type": "text", "text": "conflict"}],
        "structuredContent": value,
        "_meta": {"com.example/revision": "rev-3", "mcp.dev/internal": "omit"},
    })
    data = json.loads(call_result(result))
    assert data == {"error": "conflict", "structuredContent": value,
                    "_meta": {"com.example/revision": "rev-3"}}
    assert type(data["structuredContent"]) is type(value)
    assert mcp_tool._server_error_counts["contract"] == 1
    assert mcp_tool._server_errors_all_application["contract"] is True


def test_duplicate_detection_does_not_coerce_booleans_to_numbers(call_result):
    for text_value, value in [({"enabled": 1}, {"enabled": True}), ([0], [False]), (1, True)]:
        result = CallToolResult.model_validate({
            "content": [{"type": "text", "text": json.dumps(text_value)}], "structuredContent": value})
        assert json.loads(call_result(result))["structuredContent"] == value


def test_truncated_output_is_distinct_from_a_valid_string(call_result):
    oversized = "x" * (mcp_tool_content._MCP_HARD_RESULT_CAP_CHARS + 500)
    result = CallToolResult.model_validate({"content": [], "structuredContent": oversized})
    data = json.loads(call_result(result))
    assert data["structuredContentTruncated"] is True
    assert "TRUNCATED" in data["result"]
    assert len(data["result"]) < len(oversized)
    with_text = result.model_copy(update={"content": [TextContent(type="text", text="finished")]})
    assert json.loads(call_result(with_text)) == {"result": "finished", "structuredContentTruncated": True}
    preview_text = "example [MCP RESULT TRUNCATED] text"
    valid_string = CallToolResult.model_validate({
        "content": [{"type": "text", "text": "finished"}], "structuredContent": preview_text})
    assert json.loads(call_result(valid_string)) == {"result": "finished", "structuredContent": preview_text}


def test_truncating_display_text_does_not_discard_intact_structured_output(call_result):
    value = {"id": "row-7"}
    text = " " * mcp_tool_content._MCP_HARD_RESULT_CAP_CHARS + json.dumps(value)
    result = CallToolResult.model_validate({
        "content": [{"type": "text", "text": text}], "structuredContent": value})
    data = json.loads(call_result(result))
    assert "TRUNCATED" in data["result"]
    assert data["structuredContent"] == value


def test_invalid_metadata_does_not_discard_valid_structured_output(call_result):
    result = CallToolResult.model_validate({
        "content": [{"type": "text", "text": "finished"}],
        "structuredContent": {"id": "row-7"}, "_meta": {"com.example/invalid": object()},
    })
    assert json.loads(call_result(result)) == {"result": "finished", "structuredContent": {"id": "row-7"}}


def test_native_image_envelope_keeps_the_typed_result(call_result, monkeypatch):
    from tools import vision_tools

    monkeypatch.setattr(vision_tools, "_should_use_native_vision_fast_path", lambda: True)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
    result = CallToolResult.model_validate({
        "content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(png).decode()}],
        "structuredContent": "image-7",
    })
    envelope = call_result(result, "live")
    assert envelope["_multimodal"] is True
    assert any(block["type"] == "image_url" for block in envelope["content"])
    data = json.loads(envelope["text_summary"])
    assert data["structuredContent"] == "image-7"
    assert data["result"].startswith("MEDIA:")
