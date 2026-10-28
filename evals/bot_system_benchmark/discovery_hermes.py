"""Run Hermes' production discovery functions against an external JSON fixture.

Reads one request from stdin and writes one JSON report to stdout. Repository and
fixture paths are supplied by the caller; no model or connected service is used.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any


def benchmark(request: dict[str, Any]) -> dict[str, Any]:
    repository = Path(request["repository_path"]).resolve()
    if not (repository / "tools" / "tool_search_catalog.py").is_file():
        raise ValueError("repository_path must name the Hermes checkout")
    sys.path.insert(0, str(repository))
    from tools import registry as registry_module
    from tools.registry import ToolRegistry
    from tools.tool_search import _shared_tool_record
    from tools.tool_search_catalog import build_catalog, search_catalog
    try:
        from tools.tool_search_results import SearchResultProjection
    except ModuleNotFoundError as error:
        if error.name != "tools.tool_search_results":
            raise
        SearchResultProjection = None

    limit = int(request.get("limit", 5))
    if not 1 <= limit <= 10:
        raise ValueError("the shared discovery limit must be between 1 and 10")
    warmups = max(0, int(request.get("warmups", 2)))
    repetitions = max(1, int(request.get("repetitions", 10)))
    definitions = [
        {"type": "function", "function": {
            "name": entry["name"], "description": entry["description"],
            "parameters": entry["parameters"],
        }}
        for entry in request["catalog"]
    ]
    registry = ToolRegistry()
    for definition in definitions:
        function = definition["function"]
        # A source label already present as a name token adds no extra search
        # text. Archive filler entries share their leading "archive" namespace.
        namespace = re.split(r"[_.:-]", function["name"], maxsplit=1)[0]
        registry.register(name=function["name"], toolset=f"mcp-{namespace}",
                          schema=function, handler=lambda args: "{}")
    registry_module.registry = registry
    registry_size = len(registry.get_all_entries())

    started = time.perf_counter_ns()
    build_catalog(definitions)
    catalog_build_ms = (time.perf_counter_ns() - started) / 1_000_000

    def search(query: str) -> tuple[list[str], list[str], dict[str, dict]]:
        # The production bridge rebuilds its catalog for each call. Include that
        # work rather than comparing a reused Hermes index with OpenBot's full search.
        hits = search_catalog(build_catalog(definitions), query, limit=limit)
        if SearchResultProjection is None:
            records = {entry.name: _shared_tool_record(entry) for entry in hits}
        else:
            projection = SearchResultProjection()
            projection.add(hits, query)
            records = projection.tools
        schemas = {name: record["parameters"] if "parameters" in record else record["inputSchema"]
                   for name, record in records.items() if "parameters" in record or "inputSchema" in record}
        return list(records), list(schemas), schemas

    results = []
    for query in request["queries"]:
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise ValueError("queries must contain strings of 1 to 200 characters")
        for _ in range(warmups):
            search(query)
        latencies = []
        names: list[str] = []
        schema_names: list[str] = []
        schemas: dict[str, dict] = {}
        for _ in range(repetitions):
            started = time.perf_counter_ns()
            names, schema_names, schemas = search(query)
            latencies.append((time.perf_counter_ns() - started) / 1_000_000)
        results.append({"query": query, "names": names, "schema_names": schema_names, "schemas": schemas,
                        "latencies_ms": latencies})
    return {
        "implementation": "hermes",
        "repository_path": str(repository),
        "seam": "synthetic definitions registered in a fresh real ToolRegistry and passed to production catalog/ranking and its current model-visible projection; handlers are never invoked",
        "timing_boundary": "stateless catalog build, production ranking/projection and neutral schema extraction; JSON report serialization excluded",
        "catalog_build_ms": catalog_build_ms,
        "catalog_size": len(definitions),
        "registry_size": registry_size,
        "results": results,
    }


if __name__ == "__main__":
    json.dump(benchmark(json.load(sys.stdin)), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
