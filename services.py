"""Domain services of stapel-geo: proximity search and location resolution.

Every search verb goes through the **search facade**
(``stapel_geo.search.get_backend()`` — ``STAPEL_GEO["SEARCH_BACKEND"]``),
so the comm Functions and the HTTP views share one code path regardless
of the engine (Postgres geohash by default, Redis GEOSEARCH, ...).

Backends answer in ``(uuid_key, distance_km)`` hits; this layer joins the
keys back to ``Location`` rows (order-preserving) and shapes the compact
cross-service summary dicts.
"""
from __future__ import annotations

from typing import Optional

import pygeohash as pgh

from .conf import geo_settings
from .search import get_backend


def _get_location_by_uuid(uuid: str):
    """Resolve a Location by cross-service UUID, or ``None`` (ORM)."""
    from .models import Location

    return Location.objects.filter(uuid=uuid).first()


def _rows_for_hits(hits: list) -> list:
    """Join backend hits back to Location rows, preserving hit order.

    *hits* are ``(uuid_key, distance_km)`` pairs or bare ``uuid_key``
    strings (bbox). Rows get a ``distance_km`` attribute attached
    (``None`` for distance-less verbs). Keys unknown to the table are
    dropped — the side-index backends may lag the source of truth.
    """
    from .models import Location

    normalized = [
        (hit, None) if isinstance(hit, str) else (hit[0], hit[1]) for hit in hits
    ]
    keys = [key for key, _ in normalized]
    by_uuid = {str(row.uuid): row for row in Location.objects.filter(uuid__in=keys)}
    rows = []
    for key, distance in normalized:
        row = by_uuid.get(key)
        if row is None:
            continue
        row.distance_km = distance
        rows.append(row)
    return rows


def _summary(location, distance_km: Optional[float] = None) -> dict:
    """Shape a Location into the compact cross-service summary dict."""
    return {
        "uuid": str(location.uuid),
        "name": location.name,
        "country": location.country,
        "geohash": location.geohash,
        "distance_km": distance_km,
    }


# ---------------------------------------------------------------------------
# nearby
# ---------------------------------------------------------------------------


def nearby_rows_by_coords(
    lat: float, lon: float, precision: Optional[int] = None, limit: Optional[int] = None
) -> list:
    """Location rows nearest to a coordinate pair, nearest-first."""
    hits = get_backend().nearby(
        lat, lon, limit=_clamp_limit(limit), precision=precision
    )
    return _rows_for_hits(hits)


def nearby_rows_by_geohash(gh: str, limit: Optional[int] = None) -> list:
    """Location rows nearest to a geohash (decoded to its cell centre)."""
    lat, lon = pgh.decode(gh)
    hits = get_backend().nearby(
        lat, lon, limit=_clamp_limit(limit), precision=len(gh)
    )
    return _rows_for_hits(hits)


def nearby_by_coords(
    lat: float, lon: float, precision: Optional[int] = None, limit: Optional[int] = None
) -> list[dict]:
    return [
        _summary(row, row.distance_km)
        for row in nearby_rows_by_coords(lat, lon, precision, limit)
    ]


def nearby_by_geohash(gh: str, limit: Optional[int] = None) -> list[dict]:
    return [
        _summary(row, row.distance_km) for row in nearby_rows_by_geohash(gh, limit)
    ]


# ---------------------------------------------------------------------------
# radius / bbox
# ---------------------------------------------------------------------------


def radius(
    lat: float, lon: float, radius_km: float, limit: Optional[int] = None
) -> list[dict]:
    """Every location within *radius_km*, ascending distance (not top-K)."""
    hits = get_backend().radius(lat, lon, radius_km, limit=_clamp_limit(limit))
    return [_summary(row, row.distance_km) for row in _rows_for_hits(hits)]


def bbox(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    limit: Optional[int] = None,
) -> list[dict]:
    """Locations inside the rectangle (``min_lon > max_lon`` = antimeridian)."""
    hits = get_backend().bbox(
        min_lat, min_lon, max_lat, max_lon, limit=_clamp_limit(limit)
    )
    return [_summary(row) for row in _rows_for_hits(hits)]


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


def resolve(uuid: str) -> dict:
    """Resolve a Location UUID to a summary for cross-service references.

    Returns ``{"found": False, "uuid": ...}`` when the UUID is unknown —
    a missing location is a normal answer, not an error.
    """
    location = _get_location_by_uuid(uuid)
    if location is None:
        return {"found": False, "uuid": uuid}
    return {
        "found": True,
        "uuid": str(location.uuid),
        "name": location.name,
        "country": location.country,
        "type": location.type,
        "display_name": location.display_name,
    }


def _clamp_limit(limit: Optional[int]) -> int:
    if limit is None:
        return geo_settings.NEARBY_LIMIT
    return max(1, min(int(limit), geo_settings.NEARBY_MAX_LIMIT))


__all__ = [
    "nearby_by_geohash",
    "nearby_by_coords",
    "nearby_rows_by_geohash",
    "nearby_rows_by_coords",
    "radius",
    "bbox",
    "resolve",
]
