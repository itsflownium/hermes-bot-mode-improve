"""Publish a complete Bot Mode reply once, across independent processes."""

from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
from typing import Any
import uuid

from utils import fsync_directory


def publish_first_reply(target: Path, payload: dict[str, Any]) -> bool:
    # Replacing the final name after exists() can erase a winner. Link a fully
    # written private candidate instead: the filesystem arbitrates one publisher.
    from tools.bot_relay import _atomic_write_json

    candidate = target.with_name(f".pending-{uuid.uuid4().hex}.json")
    try:
        _atomic_write_json(candidate, payload)
        try:
            os.link(candidate, target)
        except FileExistsError:
            return False
        fsync_directory(target.parent)
        return True
    finally:
        # A crash can leave the private candidate; the existing *.json stale
        # sweep also covers it, without ever treating it as an envelope id.
        with suppress(OSError):
            candidate.unlink()
