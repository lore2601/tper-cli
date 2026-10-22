"""Accent- and case-insensitive text search with small-typo tolerance."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from difflib import SequenceMatcher
from typing import TypeVar

from tper_cli.errors import AmbiguousError, NotFoundError

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


def pick(names: list[str], query: str, *, noun: str, hint: str) -> str:
    """The one name that ``query`` clearly refers to, or an error that says why not."""
    ranked = rank(query, names, lambda n: (n,), limit=6)
    if not ranked:
        raise NotFoundError(f"No {noun} matches {query!r}", hint=hint, reason=f"{noun}NotFound")
    top = ranked[0][0]
    close = [n for s, n in ranked if s >= top - 1e-9]
    if len(close) == 1 and (len(ranked) == 1 or top - ranked[1][0] >= 10 or top >= 100):
        return close[0]
    raise AmbiguousError(
        f"{query!r} matches several {noun}s",
        hint="Use the exact name of one of the candidates.",
        details={"candidates": [n for _, n in ranked[:5]]},
    )
