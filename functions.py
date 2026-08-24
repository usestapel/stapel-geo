"""comm Function surface of stapel-geo.

Synchronous, name-addressed Functions let other modules query geo without
importing it (comm-by-name):

- ``geo.nearby``  — top-K proximity search (listings' "near me" filters).
- ``geo.radius``  — every location within a radius (not top-K).
- ``geo.bbox``    — locations inside a rectangle (map viewport queries).
- ``geo.geohash_encode`` — pure lat/lon -> geohash (consumers stamp their
  own rows, e.g. listings' ``geohash`` column, without importing geo).
- ``geo.resolve`` — validate/expand a location UUID for address consumers.
- ``geo.geocode`` — address text -> normalized places (forward geocoding).
- ``geo.reverse_geocode`` — a coordinate -> one confirmable address.
- ``geo.map_config`` — the basemap/picker configuration a server-rendered
  host needs before it can draw a map.

The three geocoding Functions go through the same cached, ledgered
service path as the HTTP proxy, so a module calling by name is subject to
the same accounting as a browser calling the endpoint.

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


@function("geo.geocode", schema=_schema("geo.geocode"))
def geocode_function(payload: dict) -> dict:
    """Forward-geocode address text (cached, ledgered, provider-agnostic).

    Payload: ``{"q": "<text>"[, "lang", "limit", "bbox", "bias_lat",
    "bias_lon"]}``. Returns the normalized GeoJSON FeatureCollection as a
    dict: ``{"type", "features": [...], "lang"}``. Every feature's
    ``properties.formatted`` is the ready-to-display line.

    Raises ``GeocoderError`` when the provider is unreachable — a caller
    over comm sees the failure rather than an empty result set, because
    "no matches" and "the geocoder is down" are different answers.
    """
    from dataclasses import asdict

    from .geocoding.service import geocode

    response = geocode(
        "search",
        query=payload["q"],
        lang=payload.get("lang"),
        limit=payload.get("limit"),
        bbox=payload.get("bbox"),
        bias_lat=payload.get("bias_lat"),
        bias_lon=payload.get("bias_lon"),
    )
    return asdict(response)


@function("geo.reverse_geocode", schema=_schema("geo.reverse_geocode"))
def reverse_geocode_function(payload: dict) -> dict:
    """Turn a coordinate into one confirmable address (the resolve verb).

    Payload: ``{"lat": <num>, "lon": <num>[, "lang", "limit", "nearest"]}``.
    Returns the ``PlaceResolution`` dict: the point, its geohash, the
    display line, the address components, the best feature, the
    alternatives, and (when ``nearest`` > 0) nearby known locations.

    This is what a listings backend calls to stamp a human address onto a
    row it only has coordinates for.
    """
    from dataclasses import asdict

    from .geocoding.service import resolve_point

    resolution = resolve_point(
        payload["lat"],
        payload["lon"],
        lang=payload.get("lang"),
        limit=payload.get("limit"),
        nearest=payload.get("nearest", 0),
    )
    return asdict(resolution)


@function("geo.map_config", schema=_schema("geo.map_config"))
def map_config_function(payload: dict) -> dict:
    """The basemap + picker configuration (no arguments, no DB, no network).

    Returns the same payload as ``GET /geo/api/v1/map/config`` — tile
    template, the attribution the licence obliges the map to show, the
    zoom envelope, the operating bbox and the search-as-you-type
    discipline — for hosts that render the page server-side.
    """
    from dataclasses import asdict

    from .basemap import build_map_config

    return asdict(build_map_config())


__all__ = [
    "nearby_function",
    "radius_function",
    "bbox_function",
    "geohash_encode_function",
    "resolve_function",
    "geocode_function",
    "reverse_geocode_function",
    "map_config_function",
]
