"""Discovery tolerates request wrappers and returns bounded intact local schemas."""

import copy
import json
from types import SimpleNamespace

import pytest

from tools import tool_search
from tools.registry import ToolRegistry


@pytest.fixture
def search(monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr("tools.registry.registry", registry)
    config = tool_search.ToolSearchConfig.from_raw({})
    monkeypatch.setattr(tool_search, "load_config_readonly", lambda: config)

    def run(definitions, queries):
        for definition in definitions:
            function = definition["function"]
            registry.register(name=function["name"], toolset="mcp-search-contract",
                              schema=function, handler=lambda args: "{}")
        return json.loads(tool_search.dispatch_tool_search(
            {"queries": queries}, current_tool_defs=definitions, config=config))
    return run


def _tool(name, description, parameters=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": parameters if parameters is not None else {
            "type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]},
    }}


def test_request_wrappers_do_not_hide_capabilities_or_admit_unknown_services(search):
    definitions = [_tool("mcp__forge__create_ticket", "Create a ticket in Forge.")]
    queries = ["forge create ticket", "Would you kindly forge create ticket for me?",
               "kindly absentservice create ticket for me"]
    data = search(definitions, queries)
    assert data["results"][0]["matches"] == data["results"][1]["matches"] == ["mcp__forge__create_ticket"]
    assert data["results"][2]["matches"] == []


def test_request_wrapper_handling_keeps_domain_words(search):
    definitions = [_tool("mcp__bus__read_can_messages", "Read messages from the CAN bus.")]
    data = search(definitions, ["please bus read can messages", "please bus read unknownbus messages"])
    assert data["results"][0]["matches"] == ["mcp__bus__read_can_messages"]
    assert data["results"][1]["matches"] == []


def test_later_strong_query_promotes_one_shared_record_to_the_intact_schema(search):
    parameters = {"type": "object", "properties": {
        "mode": {"enum": ["fast", "safe"]},
        "options": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/options"}]},
        "remote": {"$ref": "https://schemas.example.invalid/options.json"},
    }, "$defs": {"options": {"type": "object", "additionalProperties": False}},
        "required": ["mode"], "additionalProperties": False}
    definitions = [_tool("mcp__forge__create_ticket", "Create a ticket in Forge.", parameters)]
    original = copy.deepcopy(definitions)
    data = search(definitions, ["forge", "mcp__forge__create_ticket", "forge create tickets"])
    assert list(data["tools"]) == ["mcp__forge__create_ticket"]
    record = data["tools"]["mcp__forge__create_ticket"]
    assert record["parameters"] == parameters
    assert "schema_hint" not in record
    assert definitions == original


def test_schema_count_and_utf8_budget_omit_whole_schemas_and_allow_smaller_ones(search):
    large = {"type": "object", "description": "界" * 6000, "properties": {}}
    names = [f"mcp__forge__operation_{index}" for index in range(5)]
    missing = _tool("mcp__forge__missing_schema", "Forge operation.")
    missing["function"].pop("parameters")
    invalid = _tool("mcp__forge__invalid_schema", "Forge operation.", {"x-invalid": object()})
    definitions = [missing, invalid, _tool(names[0], "Forge operation.", large)] + [
        _tool(name, "Forge operation.") for name in names[1:]]
    omitted = [missing["function"]["name"], invalid["function"]["name"], names[0]]
    data = search(definitions, omitted[:2] + names)
    records = data["tools"]
    for name in omitted:
        assert "parameters" not in records[name]
        assert "tool_describe" in records[name]["schema_hint"]
    exposed = [record["parameters"] for record in records.values() if "parameters" in record]
    assert len(exposed) == 3
    assert sum(len(json.dumps(schema, ensure_ascii=False).encode("utf-8")) for schema in exposed) <= 16_384
    assert "parameters" not in records[names[-1]]
    assert "tool_describe" in records[names[-1]]["schema_hint"]


def test_live_catalog_changes_and_token_mutations_do_not_reuse_stale_search_text():
    definitions = [_tool("mcp__forge__inspect", "Inspect a ticket.")]
    first = tool_search.build_catalog(definitions)
    first[0]._tokens.append("injectedword")
    second = tool_search.build_catalog(definitions)
    assert tool_search.search_catalog(second, "injectedword") == []
    definitions[0]["function"]["description"] = "Inspect an invoice."
    third = tool_search.build_catalog(definitions)
    assert tool_search.search_catalog(third, "invoice")
    assert tool_search.search_catalog(third, "ticket") == []


def test_hosted_search_does_not_fetch_or_advertise_local_schema_readiness():
    queries_seen = []

    def remote_search(queries):
        queries_seen.extend(queries)
        return SimpleNamespace(failure=None, payload={
            "schemas": {"create_ticket": {"connector": "forge", "description": "Create a ticket in Forge.",
                                            "input_schema": {"type": "object", "properties": {}}}},
            "results": [{"tools": ["create_ticket"]}],
        })

    definitions = [{"type": "function", "function": {"name": "manage_connections", "parameters": {}}}]
    data = json.loads(tool_search.dispatch_tool_search(
        {"queries": ["forge create ticket"]}, current_tool_defs=definitions,
        config=tool_search.ToolSearchConfig.from_raw({}), connector_search=remote_search))
    assert queries_seen == [{"use_case": "forge create ticket"}]
    assert data["tools"]
    for record in data["tools"].values():
        assert record["source"] == "connectors"
        assert "parameters" not in record
        assert "tool_describe" in record["schema_hint"]
