"""The search-backend protocol — three verbs, engine-agnostic, GDAL-free.

Hits are ``(key, distance_km)`` pairs where *key* is the searched corpus's
stable identifier — for the ``Location`` corpus that is ``str(Location.
uuid)`` (the module's cross-service reference; a geohash is not unique per
row, so it cannot be the hit key). The service layer joins keys back to
rows; backends never shape summaries.

Signatures follow geo-v2-redesign.md §2.2. ``precision`` only applies to
``nearby`` (geohash-based backends use it as the starting cell size;
engine-native backends may ignore it).
"""
from __future__ import annotations

from typing import Protocol


class GeoSearchBackend(Protocol):
    """Swappable proximity-search engine (``STAPEL_GEO["SEARCH_BACKEND"]``)."""

    def nearby(
        self, lat: float, lon: float, *, limit: int, precision: int | None = None
    ) -> list[tuple[str, float]]:
        """Top-``limit`` nearest candidates: ``(key, distance_km)`` ascending."""
        ...

    def radius(
        self, lat: float, lon: float, radius_km: float, *, limit: int | None = None
    ) -> list[tuple[str, float]]:
        """Every candidate within ``radius_km`` (not top-K), ascending distance."""
        ...

    def bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        *,
        limit: int | None = None,
    ) -> list[str]:
        """Candidate keys inside the rectangle (``min_lon > max_lon`` =
        the box crosses the antimeridian)."""
        ...


__all__ = ["GeoSearchBackend"]
