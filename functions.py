"""comm Function surface of stapel-geo.

Synchronous, name-addressed Functions let other modules query geo without
importing it (comm-by-name):

- ``geo.nearby``  — top-K proximity search (listings' "near me" filters).
- ``geo.radius``  — every location within a radius (not top-K).
- ``geo.bbox``    — locations inside a rectangle (map viewport queries).
- ``geo.geohash_encode`` — pure lat/lon -> geohash (consumers stamp their
  own rows, e.g. listings' ``geohash`` column, without importing geo).
- ``geo.resolve`` — validate/expand a location UUID for address consumers.

``nearby``/``radius``/``bbox`` all call the **search facade**
(``stapel_geo.search.get_backend()``) via the service layer — one code
path regardless of the configured backend.

Each Function carries a JSON schema in ``schemas/functions/``; the
conftest runs with ``VALIDATE_SCHEMAS`` on, so a payload drifting from its
contract fails loudly. Registration happens on import from
``apps.py:ready()``. Handlers import the service layer lazily.
"""
import json
from pathlib import Path

from stapel_core.comm import function

_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas" / "functions"


def _schema(name: str) -> dict:
    return json.loads((_SCHEMAS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@function("geo.nearby", schema=_schema("geo.nearby"))
def nearby_function(payload: dict) -> dict:
    """Proximity search by coordinates or geohash (top-K nearest).

    Payload: ``{"lat": <num>, "lon": <num>}`` or ``{"geohash": "<str>"}``,
    plus optional ``precision`` (coords only) and ``limit``. Returns
    ``{"results": [{uuid, name, country, geohash, distance_km}, ...]}``
    nearest-first; ``distance_km`` is exact haversine.
    """
    from . import services

    limit = payload.get("limit")
    if "geohash" in payload:
        results = services.nearby_by_geohash(payload["geohash"], limit)
    else:
        results = services.nearby_by_coords(
            payload["lat"], payload["lon"], payload.get("precision"), limit
        )
    return {"results": results}


@function("geo.radius", schema=_schema("geo.radius"))
def radius_function(payload: dict) -> dict:
    """Every location within ``radius_km`` of a point, ascending distance.

    Payload: ``{"lat": <num>, "lon": <num>, "radius_km": <num>[, "limit"]}``.
    Returns the same summary rows as ``geo.nearby`` — but membership is
    "inside the circle", not top-K.
    """
    from . import services

    results = services.radius(
        payload["lat"], payload["lon"], payload["radius_km"], payload.get("limit")
    )
    return {"results": results}


@function("geo.bbox", schema=_schema("geo.bbox"))
def bbox_function(payload: dict) -> dict:
    """Locations inside a lat/lon rectangle (map viewport).

    Payload: ``{"min_lat", "min_lon", "max_lat", "max_lon"[, "limit"]}``.
    ``min_lon > max_lon`` means the box crosses the antimeridian. Result
    rows carry ``distance_km: null`` (a box has no centre distance).
    """
    from . import services

    results = services.bbox(
        payload["min_lat"],
        payload["min_lon"],
        payload["max_lat"],
        payload["max_lon"],
        payload.get("limit"),
    )
    return {"results": results}


@function("geo.geohash_encode", schema=_schema("geo.geohash_encode"))
def geohash_encode_function(payload: dict) -> dict:
    """Encode a coordinate pair to a geohash (pure arithmetic, no DB).

    Payload: ``{"lat": <num>, "lon": <num>[, "precision": 1-12]}``.
    Returns ``{"geohash": "<str>"}``. This is how consumers (listings)
    stamp geohashes onto their own rows without importing stapel_geo.
    """
    from . import geohash
    from .conf import geo_settings

    precision = payload.get("precision") or geo_settings.GEOHASH_PRECISION
    return {"geohash": geohash.encode(payload["lat"], payload["lon"], precision)}


@function("geo.resolve", schema=_schema("geo.resolve"))
def resolve_function(payload: dict) -> dict:
    """Resolve a location UUID to a summary (cross-service reference check).

    Payload: ``{"uuid": "<uuid>"}``. Returns ``{"found": bool, "uuid": ...}``
    and, when found, ``name``/``country``/``type``/``display_name``.
    """
    from . import services

    return services.resolve(payload["uuid"])


__all__ = [
    "nearby_function",
    "radius_function",
    "bbox_function",
    "geohash_encode_function",
    "resolve_function",
]
