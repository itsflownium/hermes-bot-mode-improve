"""Immutable candidate math must preserve mutable catalog and schema behavior."""

from tools.tool_search_catalog import (
    _corpus_stats,
    _tokenize,
    build_catalog,
    search_catalog,
)


def _definition(name, description):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"subject": {"type": "string"}},
            },
        },
    }


def test_cached_math_cannot_leak_mutations_or_retain_old_schema_constraints():
    definitions = [
        _definition("invoice_list", "List billing invoices."),
        _definition("ticket_list", "List support tickets."),
    ]
    catalog = build_catalog(definitions)
    lengths, _average, frequencies, _count = _corpus_stats(catalog)
    lengths.clear()
    frequencies.clear()
    assert (
        search_catalog(build_catalog(definitions), "billing invoices")[0].name
        == "invoice_list"
    )
    definitions[0]["function"]["parameters"]["properties"]["subject"]["minLength"] = 7
    rebuilt = build_catalog(definitions)
    hit = search_catalog(rebuilt, "billing invoices")[0]
    assert (
        hit.schema["function"]["parameters"]["properties"]["subject"]["minLength"] == 7
    )
    catalog[1]._tokens.extend(_tokenize("newintent"))
    assert search_catalog(catalog, "newintent")[0].name == "ticket_list"
    assert search_catalog(rebuilt, "newintent") == []


def test_candidate_index_preserves_ties_membership_and_exact_name_exemption():
    definitions = [
        _definition(name, "Inspect shared artifact.")
        for name in ("first", "second", "third")
    ]
    catalog = build_catalog(definitions)
    assert [entry.name for entry in search_catalog(catalog, "shared artifact")] == [
        "first",
        "second",
        "third",
    ]
    assert [entry.name for entry in search_catalog(catalog[1:], "shared artifact")] == [
        "second",
        "third",
    ]
    catalog[1].name = "EXACT_RENAMED"
    assert search_catalog(catalog, "exact_renamed")[0] is catalog[1]
    catalog.pop(1)
    assert search_catalog(catalog, "exact_renamed") == []
