"""Domain services of stapel-geo: proximity search and location resolution.

The proximity algorithm itself lives in the GDAL-free ``geohash`` module;
this layer only supplies the ORM query that turns a geohash prefix into
candidate ``Location`` rows and shapes results for the comm/HTTP surface.
The ``Location`` model is imported lazily (inside the query helpers), so
importing this module does not require GDAL — the comm Functions can be
exercised with the query helpers monkeypatched.
"""
from __future__ import annotations

from typing import Optional

from . import geohash
from .conf import geo_settings


def _fetch_prefix(prefix: str) -> list:
    """Every Location whose stored geohash starts with *prefix* (ORM)."""
    from .models import Location

    return list(Location.objects.filter(geohash__startswith=prefix))


def _get_location_by_uuid(uuid: str):
    """Resolve a Location by cross-service UUID, or ``None`` (ORM)."""
    from .models import Location

    return Location.objects.filter(uuid=uuid).first()


def _summary(location, distance_km: Optional[float] = None) -> dict:
    """Shape a Location into the compact cross-service summary dict."""
    return {
        "uuid": str(location.uuid),
        "name": location.name,
        "country": location.country,
        "geohash": location.geohash,
        "distance_km": distance_km,
    }


def nearby_by_geohash(gh: str, limit: Optional[int] = None) -> list[dict]:
    """Locations nearest to geohash *gh*, nearest-first, each with distance_km."""
    limit = _clamp_limit(limit)
    ranked = geohash.nearby(gh, _fetch_prefix, limit)
    return [_summary(loc, distance) for loc, distance in ranked]


def nearby_by_coords(
    lat: float, lon: float, precision: Optional[int] = None, limit: Optional[int] = None
) -> list[dict]:
    """Locations nearest to a coordinate pair (encoded to a geohash first)."""
    precision = precision or geo_settings.NEARBY_PRECISION
    precision = max(1, min(12, precision))
    return nearby_by_geohash(geohash.encode(lat, lon, precision), limit)


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


__all__ = ["nearby_by_geohash", "nearby_by_coords", "resolve"]
