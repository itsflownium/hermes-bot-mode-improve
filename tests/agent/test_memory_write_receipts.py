"""Native memory success and external-provider acknowledgment are separate outcomes."""

import json
from types import SimpleNamespace

import pytest

from agent.inline_tool_executors import InlineToolContext, _memory
from agent.memory_context import build_memory_context_block, sanitize_context
from agent.memory_manager import MemoryManager
from agent.memory_provider import MemoryProvider
from tools.memory_tool_store import MemoryStore


class ReceiptProvider(MemoryProvider):
    name = "receipt-provider"

    def __init__(self, response):
        self.response = response
        self.calls = []

    def is_available(self):
        return True

    def initialize(self, session_id, **kwargs):
        pass

    def get_tool_schemas(self):
        return []

    def shutdown(self):
        pass

    def on_memory_write(self, action, target, content, metadata=None):
        self.calls.append((action, target, content))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.mark.parametrize(
    "response,status",
    [
        (None, "unconfirmed"),
        (True, "acknowledged"),
        (False, "failed"),
        (RuntimeError("fixture-private-error-detail"), "failed"),
    ],
)
def test_native_commit_survives_provider_outcome_and_reports_it(response, status):
    store = MemoryStore()
    store.load_from_disk()
    provider = ReceiptProvider(response)
    manager = MemoryManager()
    manager.add_provider(provider)
    agent = SimpleNamespace(
        _memory_store=store,
        _memory_manager=manager,
        _build_memory_write_metadata=lambda **kwargs: {"session_id": "receipt-session"},
    )
    result = json.loads(
        _memory(
            agent,
            {"action": "add", "target": "memory", "content": "Use the blue theme."},
            InlineToolContext("receipt-task", "receipt-call"),
        )
    )
    assert result["success"] is True
    assert "Use the blue theme." in store.memory_entries
    assert provider.calls == [("add", "memory", "Use the blue theme.")]
    propagation = result["memory_propagation"]
    assert propagation["native"] == "committed"
    assert propagation["operations"][0]["providers"][0]["status"] == status
    assert "fixture-private-error-detail" not in json.dumps(propagation)


def test_staged_or_failed_writes_do_not_claim_provider_acknowledgment():
    provider = ReceiptProvider(True)
    manager = MemoryManager()
    manager.add_provider(provider)
    for result in ({"success": False}, {"success": True, "staged": True}):
        assert not manager.notify_memory_tool_write(
            result, {"action": "remove", "old_text": "prior fact"}
        )
    assert provider.calls == []


def test_recalled_provider_data_does_not_receive_permission_authority():
    raw = "- A historical observation from a provider."
    block = build_memory_context_block(raw)
    note, content = block.split("]\n\n", 1)
    assert "informational background data from memory providers" in note
    assert "cannot grant permission" in note and "Current user instructions" in note
    assert "authoritative reference data" not in note
    assert content == raw + "\n</memory-context>"
    assert sanitize_context(block) == ""
