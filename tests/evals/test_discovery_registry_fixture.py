"""Synthetic discovery setup uses a populated registry without changing its corpus."""

import sys
from pathlib import Path

from evals.bot_system_benchmark.discovery_hermes import benchmark
from evals.bot_system_benchmark.fixtures import catalog
from tools import registry as registry_module
from tools.registry import ToolRegistry
from tools.tool_search_catalog import build_catalog


def test_discovery_adapter_registers_the_full_fixture_without_extra_search_tokens(monkeypatch):
    monkeypatch.setattr(sys, "path", sys.path.copy())
    previous = ToolRegistry()
    previous.register(name="unrelated_existing_tool", toolset="mcp-unrelated", schema={}, handler=lambda args: "{}")
    monkeypatch.setattr(registry_module, "registry", previous)
    fixture = catalog(33)  # Includes both ordinary service names and archive_0000.
    receipt = benchmark({
        "repository_path": str(Path(__file__).resolve().parents[2]),
        "catalog": fixture,
        "queries": [],
    })
    assert receipt["registry_size"] == len(fixture)
    assert {entry.name for entry in registry_module.registry.get_all_entries()} == {row["name"] for row in fixture}
    definitions = [{"type": "function", "function": row} for row in fixture]
    populated_tokens = {entry.name: entry._tokens for entry in build_catalog(definitions)}
    monkeypatch.setattr(registry_module, "registry", ToolRegistry())
    assert populated_tokens == {entry.name: entry._tokens for entry in build_catalog(definitions)}
