"""Configured routing reaches the real request builder and follows model changes."""

import copy

import pytest

from agent.provider_routing import validate_sort, validated_advanced_preferences


def test_model_preferences_reach_openrouter_wire_and_do_not_leak(monkeypatch):
    from hermes_cli.config import (
        atomic_config_write,
        get_config_path,
        load_config_readonly,
    )
    from tests.agent.test_provider_parity import _make_agent

    routing = {
        "sort": {"by": "throughput", "partition": "none"},
        "allow_fallbacks": False,
        "zdr": True,
        "enforce_distillable_text": False,
        "preferred_min_throughput": {"p50": 30, "p90": 15},
        "preferred_max_latency": 2.5,
        "max_price": {"prompt": 0, "completion": 3.0},
        "quantizations": ["fp8", "bf16"],
    }
    atomic_config_write(
        get_config_path(), {"provider_routing": {"models": {"routing-a": routing}}}
    )
    saved = copy.deepcopy(load_config_readonly()["provider_routing"])
    agent = _make_agent(monkeypatch, "openrouter", model="routing-a")
    messages = [
        {"role": "system", "content": "Frozen prefix"},
        {"role": "user", "content": "Hi"},
    ]
    original = copy.deepcopy(messages)
    try:
        assert agent._build_api_kwargs(messages)["extra_body"]["provider"] == routing
        agent.model = "routing-b"
        assert (
            not agent._build_api_kwargs(messages).get("extra_body", {}).get("provider")
        )
        agent.model = "routing-a"
        agent.provider = "openai"
        agent.base_url = "https://api.openai.com/v1"
        assert "provider" not in agent._build_api_kwargs(messages).get("extra_body", {})
        assert messages == original
        assert load_config_readonly()["provider_routing"] == saved
    finally:
        agent.close()


@pytest.mark.parametrize(
    "value",
    [
        True,
        -1,
        float("nan"),
        float("inf"),
        "30",
        [],
        {"p95": 30},
        {"p50": 30, "p90": -1},
    ],
)
def test_invalid_numeric_preferences_are_not_forwarded(value):
    assert (
        validated_advanced_preferences(
            {"preferred_min_throughput": value, "preferred_max_latency": value}
        )
        == {}
    )


def test_preference_validation_preserves_false_zero_and_detaches_containers():
    raw = {
        "allow_fallbacks": False,
        "zdr": False,
        "preferred_min_throughput": 0,
        "max_price": {"prompt": 0},
        "quantizations": ["fp8", "fp8"],
    }
    result = validated_advanced_preferences(raw)
    assert result == {**raw, "quantizations": ["fp8"]}
    result["max_price"]["prompt"] = 9
    result["quantizations"].append("bf16")
    assert raw["max_price"] == {"prompt": 0} and raw["quantizations"] == ["fp8", "fp8"]
    assert (
        validated_advanced_preferences(
            {
                "allow_fallbacks": "false",
                "max_price": {"unknown": 1},
                "quantizations": ["fp8", "invented"],
            }
        )
        == {}
    )
    assert validate_sort({"by": " LATENCY ", "partition": "model"}) == {
        "by": "latency",
        "partition": "model",
    }
    assert validate_sort({"by": "price", "partition": "invented"}) is None
    assert validate_sort({"by": "price", "unexpected": True}) is None
