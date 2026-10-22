"""Accent- and case-insensitive text search with small-typo tolerance."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from difflib import SequenceMatcher
from typing import TypeVar

T = TypeVar("T")

_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """Lower-case, strip accents and punctuation, collapse spaces."""
    decomposed = unicodedata.normalize("NFKD", text.replace("`", "'"))
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", ascii_text.lower()).strip()


def score(query: str, candidate: str) -> float:
    """0 means no match. Higher is better. Both arguments must be normalised."""
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 100.0
    if candidate.startswith(query):
        return 85.0
    q_tokens = query.split()
    c_tokens = candidate.split()
    if all(any(ct.startswith(qt) for ct in c_tokens) for qt in q_tokens):
        return 70.0 + 10.0 * (len(q_tokens) / max(len(c_tokens), 1))
    if query in candidate:
        return 60.0
    ratio = SequenceMatcher(None, query, candidate).ratio()
    return ratio * 50.0 if ratio >= 0.78 else 0.0


def rank(
    query: str,
    items: Iterable[T],
    keys: Callable[[T], Sequence[str]],
    *,
    limit: int | None = None,
) -> list[tuple[float, T]]:
    """Return ``(score, item)`` pairs, best first. ``keys`` gives the searchable names."""
    q = normalize(query)
    scored: list[tuple[float, T]] = []
    for item in items:
        best = max((score(q, normalize(k)) for k in keys(item)), default=0.0)
        if best > 0:
            scored.append((best, item))
    scored.sort(key=lambda pair: -pair[0])
    return scored[:limit] if limit else scored
