"""Two actual processes must not change an already observed Bot Mode reply."""

import json
import multiprocessing

import pytest


def _writer(
    root, envelope_id, first, first_error, first_ready, second_ready, first_observed
):
    from tools import bot_relay

    write_json = bot_relay._atomic_write_json

    def gated_write(path, payload, **kwargs):
        if first:
            first_ready.set()
            assert second_ready.wait(10), "second publisher never reached the write"
        else:
            second_ready.set()
            assert first_ready.wait(10), "first publisher never reached the write"
            assert first_observed.wait(10), "first settlement was never observed"
        write_json(path, payload, **kwargs)

    bot_relay._atomic_write_json = gated_write
    reply = "" if first == first_error else ("FIRST_ANSWER" if first else "LATE_ANSWER")
    error = ("FIRST_ERROR" if first else "LATE_ERROR") if not reply else ""
    path = bot_relay.write_reply(
        root,
        envelope_id,
        reply=reply,
        error=error,
        reason="target_busy" if error else "",
    )
    if first:
        (root / "first-observed.json").write_bytes(path.read_bytes())
        first_observed.set()


@pytest.mark.parametrize(
    "first_error",
    [False, True],
    ids=["answer-before-timeout", "refusal-before-late-answer"],
)
def test_first_observed_settlement_survives_a_concurrent_publisher(
    tmp_path, first_error
):
    context = multiprocessing.get_context("spawn")
    gates = (context.Event(), context.Event(), context.Event())
    envelope_id = "a" * 32
    processes = [
        context.Process(
            target=_writer, args=(tmp_path, envelope_id, first, first_error, *gates)
        )
        for first in (True, False)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=15)
        assert [process.exitcode for process in processes] == [0, 0]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    observed = (tmp_path / "first-observed.json").read_bytes()
    actual = (tmp_path / "bot_relay" / "replies" / f"{envelope_id}.json").read_bytes()
    assert actual == observed, (
        "a later publisher replaced a reply the waiter already observed"
    )
    assert json.loads(actual)["error"] == ("FIRST_ERROR" if first_error else "")


@pytest.mark.parametrize("failure", ["stage", "publish"])
def test_failed_publication_does_not_reserve_an_empty_reply_or_leave_candidates(
    tmp_path, monkeypatch, failure
):
    from tools import bot_relay, bot_relay_settlement

    def unavailable(*args, **kwargs):
        raise OSError("injected reply publication failure")

    with monkeypatch.context() as patch:
        if failure == "stage":
            patch.setattr(bot_relay, "_atomic_write_json", unavailable)
        else:
            patch.setattr(bot_relay_settlement.os, "link", unavailable)
        with pytest.raises(OSError, match="publication failure"):
            bot_relay.write_reply(tmp_path, "b" * 32, reply="not committed")
    directory = tmp_path / "bot_relay" / "replies"
    assert list(directory.iterdir()) == []
    recovered = bot_relay.write_reply(tmp_path, "b" * 32, reply="RECOVERED")
    independent = bot_relay.write_reply(tmp_path, "c" * 32, reply="OTHER_ENVELOPE")
    assert json.loads(recovered.read_text())["reply"] == "RECOVERED"
    assert json.loads(independent.read_text())["reply"] == "OTHER_ENVELOPE"
