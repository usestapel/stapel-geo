"""Geohash proximity math — the GDAL-free heart of nearby search.

This module never imports GeoDjango/GDAL. It depends only on ``pygeohash``
(pure geohash encoding, adjacency and haversine distance), so the whole
proximity algorithm — encode coordinates, widen the search cell through
geohash neighbours, rank by true great-circle distance — is unit-testable
without a spatial database.

The ORM layer (``stapel_geo.services``) supplies a ``fetch_prefix``
callable that turns a geohash prefix into candidate rows; everything else
here is arithmetic on strings.
"""
from __future__ import annotations

from math import inf
from typing import Callable, Iterable, Protocol, TypeVar

import pygeohash as pgh

# Per-precision cell error (metres) — the radius a geohash of *n* characters
# is guaranteed to pin a point within. Used to decide when a neighbour block
# has provably covered every candidate closer than what it already holds.
_CELL_ERROR_M = pgh.PRECISION_TO_ERROR

# The four cardinal adjacency directions pygeohash understands.
_CARDINALS = ("top", "bottom", "left", "right")


def encode(lat: float, lon: float, precision: int = 8) -> str:
    """Encode a latitude/longitude pair to a geohash of *precision* chars."""
    return pgh.encode(lat, lon, precision=precision)


def distance_km(gh_a: str, gh_b: str) -> float:
    """True great-circle distance between two geohashes, in km (haversine).

    Decodes each geohash to its cell centre and applies the haversine
    formula, so the result is a real distance — correct across the
    antimeridian and near the poles — not a prefix-similarity bucket.
    Rounded to 2 decimals.
    """
    metres = pgh.geohash_haversine_distance(gh_a, gh_b)
    return round(metres / 1000, 2)


class _HasGeohash(Protocol):
    geohash: str | None


T = TypeVar("T", bound=_HasGeohash)


def rank_by_proximity(target: str, candidates: Iterable[T]) -> list[tuple[T, float | None]]:
    """Return ``(candidate, distance_km)`` pairs sorted nearest-first.

    Candidates without a geohash sort last with ``None`` distance. The
    input geohash need not share the candidates' precision — haversine
    decodes each geohash independently of length.
    """
    scored: list[tuple[T, float | None]] = []
    for candidate in candidates:
        gh = getattr(candidate, "geohash", None)
        distance = distance_km(target, gh) if gh else None
        scored.append((candidate, distance))
    scored.sort(key=lambda pair: pair[1] if pair[1] is not None else float("inf"))
    return scored


def _neighbor_cells(prefix: str) -> tuple[list[str], bool]:
    """The prefix's cell plus its 8 geohash neighbours.

    Returns ``(cells, complete)``. ``cells`` starts with *prefix* itself
    (so the target cell is always queried first) followed by the distinct
    surrounding cells. ``complete`` is ``False`` when any neighbour could
    not be computed — pygeohash raises near the poles and refuses to wrap
    the antimeridian, so a coarse cell there does *not* actually cover its
    nominal radius, and the caller must not trust it for an early stop.
    """
    cells = [prefix]
    seen = {prefix}
    complete = True

    def adjacent(base: str, direction: str) -> str | None:
        nonlocal complete
        try:
            return pgh.get_adjacent(base, direction)
        except Exception:  # noqa: BLE001 — pole/edge cells have no neighbour
            complete = False
            return None

    north = adjacent(prefix, "top")
    south = adjacent(prefix, "bottom")
    east = adjacent(prefix, "right")
    west = adjacent(prefix, "left")

    diagonals: list[str | None] = []
    for vertical in (north, south):
        if vertical is not None:
            diagonals.append(adjacent(vertical, "left"))
            diagonals.append(adjacent(vertical, "right"))

    for cell in (north, south, east, west, *diagonals):
        if cell and cell not in seen:
            seen.add(cell)
            cells.append(cell)
    return cells, complete


def _fetch_block(prefix: str, fetch_prefix: Callable[[str], list[T]]) -> tuple[list[T], bool]:
    """Every candidate in *prefix*'s cell and its 8 neighbours, deduplicated."""
    cells, complete = _neighbor_cells(prefix)
    rows: list[T] = []
    seen: set[int] = set()
    for cell in cells:
        for row in fetch_prefix(cell):
            key = id(row)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows, complete


def nearby(
    target: str,
    fetch_prefix: Callable[[str], list[T]],
    limit: int,
) -> list[tuple[T, float | None]]:
    """Find up to *limit* candidates nearest to the *target* geohash.

    ``fetch_prefix(prefix)`` returns every candidate whose stored geohash
    starts with *prefix* (``prefix=""`` returns all candidates). Starting
    from the full target geohash we query the target cell *and its eight
    neighbours*, then widen the cell one character at a time. A level's
    result is trusted only when the neighbour block was complete (no
    pole/antimeridian gap) *and* the ``limit``-th nearest candidate lies
    within that level's guaranteed coverage radius — otherwise a closer
    candidate could sit just outside the block (across a cell boundary,
    the equator, the antimeridian, or over a pole).

    When no level can prove coverage — sparse data, or a target hard
    against a seam where geohash neighbours do not bridge — we fall back to
    an authoritative empty-prefix scan and rank the whole set. Widening by
    prefix keeps the common case index-friendly (a plain
    ``geohash__startswith`` query); the fallback guarantees correctness.
    """
    if limit <= 0:
        return []

    prefix = target
    while prefix:
        block, complete = _fetch_block(prefix, fetch_prefix)
        if complete and len(block) >= limit:
            ranked = rank_by_proximity(target, block)
            kth = ranked[limit - 1][1]
            radius_m = _CELL_ERROR_M.get(min(len(prefix), 10), inf)
            if kth is not None and kth * 1000 <= radius_m:
                return ranked[:limit]
        prefix = prefix[:-1]

    # No level could prove it held the true nearest — scan everything.
    return rank_by_proximity(target, fetch_prefix(""))[:limit]


__all__ = [
    "encode",
    "distance_km",
    "rank_by_proximity",
    "nearby",
]
