"""The spending guard must reject before inference; real streamed tool calls survive."""

import httpx
import pytest

from evals.bot_system_benchmark.model_proxy import PortalProxy
from tests.fakes.fake_llm_provider import FakeLLMServer, Text, ToolCall


def test_a_protocol_extension_cannot_raise_the_users_spending_authority(tmp_path):
    credentials = {"base_url": "http://127.0.0.1:9/v1", "api_key": "fixture-local-only"}
    pricing = {"prompt": "0.0000001", "completion": "0.0000005"}
    with pytest.raises(ValueError, match="authority"):
        PortalProxy(
            credentials,
            pricing,
            tmp_path / "ledger.json",
            allow_local=True,
            reservation_ceiling="5.01",
        )


def test_exhausted_shared_ledger_never_reaches_the_provider(tmp_path):
    with FakeLLMServer([Text("must not be called")]) as upstream:
        credentials = {"base_url": upstream.base_url, "api_key": "fixture-local-only"}
        pricing = {"prompt": "0.0000001", "completion": "0.0000005"}
        ledger = tmp_path / "ledger.json"
        with PortalProxy(credentials, pricing, ledger, allow_local=True) as proxy:
            proxy.ledger["reservations_usd"] = "4.50"
            proxy.save()
        with PortalProxy(credentials, pricing, ledger, allow_local=True) as resumed:
            response = httpx.post(
                resumed.base_url + "/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
            assert response.status_code == 429
        assert upstream.requests == []


@pytest.mark.parametrize("streaming", [False, True])
def test_real_tool_response_is_relayed_without_scripting_model_decisions(
    tmp_path, streaming
):
    from openai import OpenAI

    expected = {"path": "BLOCKER.md", "content": "Need source.csv with date and value."}
    with FakeLLMServer([ToolCall("write", expected)]) as upstream:
        credentials = {"base_url": upstream.base_url, "api_key": "fixture-local-only"}
        pricing = {"prompt": "0.0000001", "completion": "0.0000005"}
        with PortalProxy(
            credentials, pricing, tmp_path / "ledger.json", allow_local=True
        ) as proxy:
            with OpenAI(
                base_url=proxy.base_url, api_key="fixture-local-only", max_retries=0
            ) as client:
                response = client.chat.completions.create(
                    model="fixture",
                    messages=[{"role": "user", "content": "Explain the blocker."}],
                    tools=[
                        {
                            "type": "function",
                            "function": {
                                "name": "write",
                                "description": "Write a file",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "path": {"type": "string"},
                                        "content": {"type": "string"},
                                    },
                                },
                            },
                        }
                    ],
                    stream=streaming,
                )
                if streaming:
                    calls = [
                        call
                        for chunk in response
                        for choice in chunk.choices
                        for call in (choice.delta.tool_calls or [])
                    ]
                    call = calls[0]
                else:
                    call = response.choices[0].message.tool_calls[0]
            import json

            assert call.function.name == "write"
            assert json.loads(call.function.arguments) == expected
            assert len(upstream.requests) == 1
            assert proxy.ledger["requests"][0]["status"] == "completed"
