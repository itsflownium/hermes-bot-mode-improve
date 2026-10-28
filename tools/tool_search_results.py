"""Bounded schema disclosure for strong local discovery results."""

from __future__ import annotations

import json
from typing import Any

from tools.tool_search_catalog import CatalogEntry, _query_tokens, _tokenize


_MAX_RESULT_SCHEMAS = 3
_MAX_RESULT_SCHEMA_BYTES = 16_384
_DESCRIBE_HINT = "Call tool_describe if parameter types or constraints are unknown."


def _strong_match(entry: CatalogEntry, query: str) -> bool:
    if query.strip().lower() == entry.name.lower():
        return True
    name_terms = set(_tokenize(entry.name.removeprefix("mcp__")))
    return bool(name_terms) and name_terms.issubset(_query_tokens(query))


def _schema_json(entry: CatalogEntry) -> tuple[str, int] | None:
    function = entry.schema.get("function") if isinstance(entry.schema, dict) else None
    parameters = function.get("parameters") if isinstance(function, dict) else None
    if not isinstance(parameters, dict):
        return None
    try:
        encoded = json.dumps(parameters, ensure_ascii=False, allow_nan=False)
        return encoded, len(encoded.encode("utf-8"))
    except (TypeError, ValueError, UnicodeError):
        return None


class SearchResultProjection:
    """One call's shared records and schema budget, including later-query promotions.

    Hosted search rows are summaries, so they still require tool_describe. This
    module never fetches schemas or mutates the model's provider tool definitions.
    """

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self._schema_count = 0
        self._schema_bytes = 0

    def add(self, hits: list[CatalogEntry], query: str) -> None:
        from tools.tool_search import _shared_tool_record

        for entry in hits:
            if entry.name not in self.tools:
                self.tools[entry.name] = {**_shared_tool_record(entry), "schema_hint": _DESCRIBE_HINT}
            record = self.tools[entry.name]
            if ("parameters" in record or entry.source == "connectors"
                    or self._schema_count >= _MAX_RESULT_SCHEMAS or not _strong_match(entry, query)):
                continue
            schema = _schema_json(entry)
            if schema is None:
                continue
            schema_json, size = schema
            if self._schema_bytes + size > _MAX_RESULT_SCHEMA_BYTES:
                continue
            record["parameters"] = json.loads(schema_json)
            record.pop("schema_hint", None)
            self._schema_count += 1
            self._schema_bytes += size
