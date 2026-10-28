"""Validate OpenRouter's optional provider preferences without altering prompts."""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)
_SORTS = {"price", "latency", "throughput"}
_PERCENTILES = {"p50", "p75", "p90", "p99"}
_PRICE_UNITS = {"prompt", "completion", "request", "image"}
_BOOL_FIELDS = {"allow_fallbacks", "zdr", "enforce_distillable_text"}
_PERFORMANCE_FIELDS = {"preferred_min_throughput", "preferred_max_latency"}
_QUANTIZATIONS = {
    "int4",
    "int8",
    "fp4",
    "fp6",
    "fp8",
    "fp16",
    "bf16",
    "fp32",
    "unknown",
}


def validate_sort(value: Any) -> str | dict[str, str] | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _SORTS:
            return normalized
    elif isinstance(value, dict) and value.keys() <= {"by", "partition"}:
        by = value.get("by")
        partition = value.get("partition")
        if (
            isinstance(by, str)
            and by.strip().lower() in _SORTS
            and partition in (None, "model", "none")
        ):
            return {
                "by": by.strip().lower(),
                **({"partition": partition} if partition is not None else {}),
            }
    if value is not None and value != "":
        logger.warning("Ignoring invalid OpenRouter provider sort configuration")
    return None


def _nonnegative(value: Any) -> bool:
    return (type(value) is int and value >= 0) or (
        type(value) is float and math.isfinite(value) and value >= 0
    )


def _numeric_preferences(value: Any, allowed: set[str]) -> dict | None:
    if not isinstance(value, dict) or not value or not value.keys() <= allowed:
        return None
    return dict(value) if all(_nonnegative(item) for item in value.values()) else None


def validated_advanced_preferences(raw: Any) -> dict[str, Any]:
    """Keep false/zero controls and reject invalid objects as a whole, without raw-value logs."""
    if not isinstance(raw, dict):
        return {}
    result = {key: raw[key] for key in _BOOL_FIELDS if type(raw.get(key)) is bool}
    for key in _PERFORMANCE_FIELDS:
        value = raw.get(key)
        if _nonnegative(value):
            result[key] = value
        elif (cutoffs := _numeric_preferences(value, _PERCENTILES)) is not None:
            result[key] = cutoffs
    if (price := _numeric_preferences(raw.get("max_price"), _PRICE_UNITS)) is not None:
        result["max_price"] = price
    quantizations = raw.get("quantizations")
    if (
        isinstance(quantizations, list)
        and quantizations
        and all(
            isinstance(item, str) and item in _QUANTIZATIONS for item in quantizations
        )
    ):
        result["quantizations"] = list(dict.fromkeys(quantizations))
    return result
