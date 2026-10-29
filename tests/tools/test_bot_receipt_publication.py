"""A waiting sender must not observe a writer's uncommitted receipt bytes."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from tools import bot_live_delivery as mailbox


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
def test_wait_reads_only_after_receipt_publication(tmp_path, monkeypatch, asynchronous):
    key = "a" * 32
    half_written = threading.Event()
    publish_allowed = threading.Event()
    settled = {"delivery_id": key, "status": "settled", "reply": "PONG"}
    real_enter = mailbox._FileLock.__enter__
    real_read = mailbox._read

    def publish():
        with mailbox._locked(tmp_path) as root:
            path = root / f"{key}.json"
            path.write_text('{"status":', encoding="utf-8")
            half_written.set()
            assert publish_allowed.wait(5), "reader never reached the publication boundary"
            mailbox._write(path, settled)

    def enter_reader(lock):
        # Schedule the writer to finish when the reader attempts the same lock.
        publish_allowed.set()
        return real_enter(lock)

    def read_receipt(path):
        try:
            return real_read(path)
        finally:
            # An unlocked old reader sees partial JSON; let its writer clean up.
            publish_allowed.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(publish)
        assert half_written.wait(5), "writer never entered its real mailbox lock"
        monkeypatch.setattr(mailbox._FileLock, "__enter__", enter_reader)
        monkeypatch.setattr(mailbox, "_read", read_receipt)
        try:
            result = (asyncio.run(mailbox.await_delivery_async(tmp_path, key, 5)) if asynchronous
                      else mailbox.await_delivery(tmp_path, key, 5))
        finally:
            publish_allowed.set()
            writer.result(timeout=5)
    assert result == settled
