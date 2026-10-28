"""Provider acknowledgments for native memory writes, without global erasure claims."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def notify_provider(
    provider, mode: str, action: str, target: str, content: str, metadata: dict
) -> dict:
    receipt = {"provider": str(provider.name), "status": "unconfirmed"}
    try:
        if mode == "legacy":
            acknowledgment = provider.on_memory_write(action, target, content)
        elif mode == "positional":
            acknowledgment = provider.on_memory_write(
                action, target, content, dict(metadata)
            )
        else:
            acknowledgment = provider.on_memory_write(
                action, target, content, metadata=dict(metadata)
            )
    except Exception as exc:  # health: allow BLE001 -- Plugin callbacks can raise arbitrary errors; receipts omit potentially secret exception text.
        logger.warning(
            "Memory provider %s did not acknowledge %s (%s)",
            receipt["provider"],
            action,
            type(exc).__name__,
        )
        return {**receipt, "status": "failed", "error_class": type(exc).__name__}
    if acknowledgment is True or (
        isinstance(acknowledgment, dict) and acknowledgment.get("success") is True
    ):
        receipt["status"] = "acknowledged"
    elif acknowledgment is False or (
        isinstance(acknowledgment, dict) and acknowledgment.get("success") is False
    ):
        receipt["status"] = "failed"
    return receipt


def attach_receipts(result: Any, receipts: Any) -> Any:
    if not isinstance(receipts, list) or not receipts:
        return result
    payload = json.loads(result) if isinstance(result, str) else result
    if (
        not isinstance(payload, dict)
        or payload.get("success") is not True
        or payload.get("staged") is True
    ):
        return result
    enriched = {
        **payload,
        "memory_propagation": {
            "native": "committed",
            "operations": receipts,
            "scope": "Native store and reported provider callbacks; active context, backups and derived copies are not certified erased.",
        },
    }
    return (
        json.dumps(enriched, ensure_ascii=False)
        if isinstance(result, str)
        else enriched
    )
