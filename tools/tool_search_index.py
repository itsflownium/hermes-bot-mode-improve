"""Bounded immutable search math; never retains schemas, live entries, or scope authority."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CorpusIndex:
    lengths: tuple[int, ...]
    average: float
    frequencies: Mapping[str, int]
    postings: Mapping[str, tuple[int, ...]]


def _build_index(documents: tuple[tuple[str, ...], ...]) -> CorpusIndex:
    postings: dict[str, list[int]] = {}
    for position, tokens in enumerate(documents):
        for token in set(tokens):
            postings.setdefault(token, []).append(position)
    lengths = tuple(map(len, documents))
    return CorpusIndex(
        lengths,
        sum(lengths) / max(len(lengths), 1),
        MappingProxyType(
            {token: len(positions) for token, positions in postings.items()}
        ),
        MappingProxyType(
            {token: tuple(positions) for token, positions in postings.items()}
        ),
    )


_cached_index = lru_cache(maxsize=8)(_build_index)


def corpus_index(documents: tuple[tuple[str, ...], ...]) -> CorpusIndex:
    build = (
        _cached_index
        if len(documents) <= 4096 and sum(map(len, documents)) <= 65_536
        else _build_index
    )
    return build(documents)


def _name_index(names: tuple[str, ...]) -> Mapping[str, tuple[int, ...]]:
    positions: dict[str, list[int]] = {}
    for index, name in enumerate(names):
        positions.setdefault(name.lower(), []).append(index)
    return MappingProxyType(
        {name: tuple(indices) for name, indices in positions.items()}
    )


_cached_names = lru_cache(maxsize=8)(_name_index)


def exact_positions(names: tuple[str, ...], query: str) -> tuple[int, ...]:
    build = (
        _cached_names
        if len(names) <= 4096 and sum(map(len, names)) <= 262_144
        else _name_index
    )
    return build(names).get(query, ())
