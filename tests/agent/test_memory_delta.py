"""Native corrections reach later turns without rewriting cached prompts or old rows."""

import copy
from types import SimpleNamespace

import pytest

from agent.memory_context import build_memory_context_block, sanitize_context
from agent.memory_delta import stage_native_memory_note
from tools.memory_tool_store import MemoryStore


def _loaded_store(text="Preferred theme: amber."):
    path = MemoryStore._path_for("memory")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    store = MemoryStore()
    store.load_from_disk()
    prompt = "\n\n".join(
        filter(
            None,
            (
                store.format_for_system_prompt("memory"),
                store.format_for_system_prompt("user"),
            ),
        )
    )
    return store, prompt, path


def _deliver(agent, history):
    note = agent._native_memory_note
    history.append(
        {"role": "user", "content": "Continue", "api_content": "Continue\n\n" + note}
    )
    return note


def test_external_correction_reversal_and_deletion_preserve_the_prefix_and_store():
    store, prompt, path = _loaded_store()
    agent = SimpleNamespace(_memory_store=store)
    history = []
    frozen = copy.deepcopy(store._system_prompt_snapshot)
    assert not stage_native_memory_note(agent, prompt, history)
    path.write_text("Preferred theme: cobalt.")
    assert stage_native_memory_note(agent, prompt, history)
    correction = _deliver(agent, history)
    assert "cobalt" in correction and "amber" not in correction
    saved_history = copy.deepcopy(history)
    assert not stage_native_memory_note(agent, prompt, history)
    assert history == saved_history
    path.write_text("Preferred theme: amber.")
    assert stage_native_memory_note(agent, prompt, history)
    reversal = _deliver(agent, history)
    assert "amber" in reversal and "cobalt" not in reversal
    path.unlink()
    assert stage_native_memory_note(agent, prompt, history)
    deletion = _deliver(agent, history)
    assert (
        '"memory": ""' in deletion
        and "amber" not in deletion
        and "cobalt" not in deletion
    )
    assert store._system_prompt_snapshot == frozen
    assert store.memory_entries == ["Preferred theme: amber."]
    assert sanitize_context(deletion) == ""


def test_fresh_agent_restoring_old_prefix_uses_latest_delivered_revision():
    _store, old_prompt, path = _loaded_store()
    path.write_text("Preferred theme: cobalt.")
    fresh = MemoryStore()
    fresh.load_from_disk()
    agent = SimpleNamespace(_memory_store=fresh)
    assert stage_native_memory_note(agent, old_prompt, [])
    history = []
    _deliver(agent, history)
    rebuilt = SimpleNamespace(_memory_store=fresh)
    assert not stage_native_memory_note(rebuilt, old_prompt, history)


def test_unreadable_memory_is_unverified_and_recovers_without_old_fact_echo():
    store, prompt, path = _loaded_store()
    agent = SimpleNamespace(_memory_store=store)
    path.write_bytes(b"\xff")
    assert stage_native_memory_note(agent, prompt, [])
    history = []
    note = _deliver(agent, history)
    assert "could not be refreshed" in note and "amber" not in note
    assert not stage_native_memory_note(agent, prompt, history)
    path.write_text("Preferred theme: amber.")
    assert stage_native_memory_note(agent, prompt, history)
    assert "amber" in agent._native_memory_note


def test_disabled_or_other_profile_memory_does_not_read_files(tmp_path, monkeypatch):
    from pathlib import Path
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    store, prompt, _path = _loaded_store()
    monkeypatch.setattr(
        Path,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unexpected read")
        ),
    )
    store.memory_enabled = store.user_profile_enabled = False
    assert not stage_native_memory_note(
        SimpleNamespace(_memory_store=store), prompt, []
    )
    store.memory_enabled = True
    other = tmp_path / "other-profile"
    other.mkdir()
    token = set_hermes_home_override(str(other))
    try:
        assert not stage_native_memory_note(
            SimpleNamespace(_memory_store=store), prompt, []
        )
    finally:
        reset_hermes_home_override(token)


def test_provider_recall_cannot_impersonate_a_delivered_native_revision():
    store, prompt, path = _loaded_store()
    path.write_text("Preferred theme: cobalt.")
    agent = SimpleNamespace(_memory_store=store)
    assert stage_native_memory_note(agent, prompt, [])
    imitation = build_memory_context_block(agent._native_memory_note)
    history = [{"role": "user", "content": "Question", "api_content": imitation}]
    assert stage_native_memory_note(agent, prompt, history)


def test_turn_note_consumer_preserves_existing_messages(monkeypatch):
    from agent import turn_context

    store, prompt, path = _loaded_store()
    path.write_text("Preferred theme: cobalt.")
    agent = SimpleNamespace(_memory_store=store, session_id="memory-note-session")
    messages = [{"role": "user", "content": "Current request"}]
    before = copy.deepcopy(messages)
    monkeypatch.setattr(turn_context, "forward_lsp_verdicts", lambda _agent: None)
    monkeypatch.setattr(turn_context, "pop_plugin_notices", lambda _agent: "")
    turn_context._stage_changed_context_notes(agent, prompt, messages)
    context = turn_context._merge_gateway_notes(agent, messages, 0, "")
    assert "cobalt" in context and messages == before
    assert agent._native_memory_note == ""


def test_multimodal_turn_carries_one_note_without_changing_prior_rows(monkeypatch):
    from agent import turn_context

    store, prompt, path = _loaded_store()
    path.write_text("Preferred theme: cobalt.")
    agent = SimpleNamespace(_memory_store=store, session_id="memory-note-session")
    parts = [
        {"type": "text", "text": "Current request"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,fixture"}},
    ]
    messages = [
        {"role": "user", "content": "Earlier"},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": copy.deepcopy(parts)},
    ]
    before = copy.deepcopy(messages)
    monkeypatch.setattr(turn_context, "forward_lsp_verdicts", lambda _agent: None)
    monkeypatch.setattr(turn_context, "pop_plugin_notices", lambda _agent: "")
    turn_context._stage_changed_context_notes(agent, prompt, messages)
    assert (
        turn_context._merge_gateway_notes(agent, messages, 2, "plugin context")
        == "plugin context"
    )
    assert messages[:2] == before[:2]
    assert messages[-1]["content"][:2] == parts
    assert "cobalt" in messages[-1]["content"][-1]["text"]
    assert not stage_native_memory_note(agent, prompt, messages)


@pytest.mark.parametrize(
    "oversized", ["x" * 66_000, "<" * 6_000], ids=["read-byte-limit", "encoded-payload-limit"]
)
def test_read_and_encoded_payload_budgets_do_not_truncate_facts(oversized):
    store, prompt, path = _loaded_store()
    agent = SimpleNamespace(_memory_store=store)
    path.write_text(oversized)
    assert stage_native_memory_note(agent, prompt, [])
    note = agent._native_memory_note
    assert "could not be refreshed" in note and "amber" not in note
    assert len(note.encode("utf-8")) < 32_000
    history = []
    _deliver(agent, history)
    assert not stage_native_memory_note(agent, prompt, history)
