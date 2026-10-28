"""Harness and malformed-output failures cannot masquerade as endpoint rejection."""

import json

import pytest

from evals.bot_system_benchmark.mcp_common import classify


def test_positive_and_rejection_contracts_use_the_same_validated_observation():
    found = {
        "tool_count": 2,
        "tool_names": ["read", "search"],
        "error": None,
        "elapsed_ms": 7.0,
    }
    assert classify(0, json.dumps(found), "catalog")["contract_pass"] is True
    assert classify(0, json.dumps(found), "reject")["contract_pass"] is False
    refused = {"tool_count": 0, "tool_names": [], "error": "not MCP", "elapsed_ms": 3.0}
    assert classify(0, json.dumps(refused), "reject")["contract_pass"] is True
    assert classify(0, json.dumps(refused), "catalog")["contract_pass"] is False
    assert classify(1, json.dumps(refused), "reject")["contract_pass"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"tool_count": True},
        {"tool_count": -1},
        {"tool_names": ["read", "read"]},
        {"tool_names": ["read", "search", "extra"]},
        {"tool_names": [""]},
        {"elapsed_ms": float("nan")},
        {"error": []},
    ],
)
def test_invalid_adapter_output_cannot_pass_either_contract(change):
    result = {
        "tool_count": 2,
        "tool_names": ["read", "search"],
        "error": None,
        "elapsed_ms": 7.0,
        **change,
    }
    for expected in ("catalog", "reject"):
        assert classify(0, json.dumps(result), expected)["contract_pass"] is False
    assert classify(0, "not json", "reject")["contract_pass"] is False
