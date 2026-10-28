"""Discovery source labels use the current registry view with bounded scope work."""

import pytest

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from tools import registry as registry_module
from tools.registry import ToolRegistry, session_tool_scope
from tools.tool_search_catalog import build_catalog, build_catalog_listing_with_form


def _definition(name):
    return {"type": "function", "function": {
        "name": name, "description": "Caller-provided search text.",
        "parameters": {"type": "object", "properties": {"caller_value": {"type": "string"}}},
    }}


def test_catalog_sources_follow_live_profile_and_session_overlays(tmp_path, monkeypatch):
    registry = ToolRegistry()
    monkeypatch.setattr(registry_module, "registry", registry)
    homes = [tmp_path / name for name in ("alpha", "beta", "global")]
    for home in homes:
        home.mkdir()
    names = ["snapshot_first", "snapshot_second"]
    definitions = [_definition(name) for name in names]

    def register(toolset, scope=None):
        for name in names:
            registry.register(name=name, toolset=toolset, scope=scope, override=True,
                              schema={"name": name, "parameters": {"properties": {"registry_value": {}}}},
                              handler=lambda args: "{}")

    register("mcp-global")
    register("mcp-alpha", homes[0])
    register("plugin-beta", homes[1])
    register("mcp-editor", "editor-session:search-snapshot")
    registry.register(name="not_in_caller_definitions", toolset="mcp-other", schema={}, handler=lambda args: "{}")

    def assert_view(home, expected, session=None):
        token = set_hermes_home_override(home)
        try:
            with session_tool_scope(session):
                catalog = build_catalog(definitions)
                listing, _form = build_catalog_listing_with_form(definitions)
            assert [entry.name for entry in catalog] == names
            assert {entry.source_name for entry in catalog} == {expected}
            assert {entry.source for entry in catalog} == {"mcp" if expected.startswith("mcp-") else "plugin"}
            assert [entry.schema for entry in catalog] == definitions
            assert all("Caller-provided" in entry.description for entry in catalog)
            assert f"{expected.removeprefix('mcp-')} tools (2):" in listing
            assert "not_in_caller_definitions" not in listing
        finally:
            reset_hermes_home_override(token)

    assert_view(homes[0], "mcp-alpha")
    assert_view(homes[1], "plugin-beta")
    assert_view(homes[0], "mcp-editor", "editor-session:search-snapshot")
    assert_view(homes[1], "plugin-beta", "editor-session:unregistered")
    assert_view(homes[2], "mcp-global")
    register("mcp-alpha-refreshed", homes[0])
    assert_view(homes[0], "mcp-alpha-refreshed")
    for name in names:
        registry.deregister(name, scope="editor-session:search-snapshot")
    assert_view(homes[0], "mcp-alpha-refreshed", "editor-session:search-snapshot")


@pytest.mark.parametrize("consumer", ["search", "listing"])
def test_catalog_scope_resolution_stays_bounded_as_tool_count_grows(monkeypatch, consumer):
    registry = ToolRegistry()
    monkeypatch.setattr(registry_module, "registry", registry)
    definitions = [_definition(f"bounded_source_{index}") for index in range(96)]
    probes = []

    def unexpected_probe():
        probes.append(True)
        raise AssertionError("source classification must not probe tool availability")

    for definition in definitions:
        name = definition["function"]["name"]
        registry.register(name=name, toolset="mcp-source-snapshot", schema=definition["function"],
                          handler=lambda args: "{}", check_fn=unexpected_probe)
    resolutions = []
    resolve_scope = registry_module.hermes_home_key

    def counted_scope(path=None):
        resolutions.append(path)
        return resolve_scope(path)

    monkeypatch.setattr(registry_module, "hermes_home_key", counted_scope)
    if consumer == "search":
        catalog = build_catalog(definitions)
        assert len(catalog) == len(definitions)
        assert {entry.source_name for entry in catalog} == {"mcp-source-snapshot"}
    else:
        listing, _form = build_catalog_listing_with_form(definitions, max_tokens=20_000)
        assert all(definition["function"]["name"] in listing for definition in definitions)
    assert not probes
    assert len(resolutions) <= 4, "registry scope work must not grow once per catalog tool"
