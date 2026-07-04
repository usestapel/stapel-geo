"""Geohash proximity math — the GDAL-free heart of nearby search.

This module never imports GeoDjango/GDAL. It depends only on ``pygeohash``
(pure geohash encoding + approximate distance), so the whole proximity
algorithm — encode coordinates, expand a prefix until enough candidates
are found, rank by approximate distance — is unit-testable without a
spatial database.

The ORM layer (``stapel_geo.services``) supplies a ``fetch_prefix``
callable that turns a geohash prefix into candidate rows; everything else
here is arithmetic on strings.
"""
from __future__ import annotations

from typing import Callable, Iterable, Protocol, TypeVar

import pygeohash as pgh


def encode(lat: float, lon: float, precision: int = 8) -> str:
    """Encode a latitude/longitude pair to a geohash of *precision* chars."""
    return pgh.encode(lat, lon, precision=precision)


def approximate_distance_km(gh_a: str, gh_b: str) -> float:
    """Approximate great-circle distance between two geohashes, in km.

    Uses ``pygeohash``'s bucketed approximation (fast, precision-tiered);
    good enough for ranking, not for exact geodesy. Rounded to 2 decimals.
    """
    metres = pgh.geohash_approximate_distance(gh_a, gh_b)
    return round(metres / 1000, 2)


class _HasGeohash(Protocol):
    geohash: str | None


T = TypeVar("T", bound=_HasGeohash)


def rank_by_proximity(target: str, candidates: Iterable[T]) -> list[tuple[T, float | None]]:
    """Return ``(candidate, distance_km)`` pairs sorted nearest-first.

    Candidates without a geohash sort last with ``None`` distance. The
    input geohash need not share the candidates' precision — the
    approximation tolerates differing lengths.
    """
    scored: list[tuple[T, float | None]] = []
    for candidate in candidates:
        gh = getattr(candidate, "geohash", None)
        distance = approximate_distance_km(target, gh) if gh else None
        scored.append((candidate, distance))
    scored.sort(key=lambda pair: pair[1] if pair[1] is not None else float("inf"))
    return scored


def nearby(
    target: str,
    fetch_prefix: Callable[[str], list[T]],
    limit: int,
) -> list[tuple[T, float | None]]:
    """Find up to *limit* candidates nearest to the *target* geohash.

    ``fetch_prefix(prefix)`` returns every candidate whose stored geohash
    starts with *prefix*. Starting from the full target geohash we shorten
    the prefix one character at a time (widening the search cell) until we
    have at least *limit* candidates or the prefix is exhausted, then rank
    the collected set by approximate distance and truncate to *limit*.

    Widening by geohash prefix is coarse but index-friendly: a plain
    ``geohash__startswith`` query, no spatial index required.
    """
    if limit <= 0:
        return []

    prefix = target
    candidates: list[T] = []
    while prefix:
        candidates = fetch_prefix(prefix)
        if len(candidates) >= limit:
            break
        prefix = prefix[:-1]

    return rank_by_proximity(target, candidates)[:limit]


__all__ = [
    "encode",
    "approximate_distance_km",
    "rank_by_proximity",
    "nearby",
]
