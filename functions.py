"""comm Function surface of stapel-geo.

Two synchronous, name-addressed Functions let other modules query geo
without importing it (comm-by-name):

- ``geo.nearby``  — proximity search for listings' radius/geo filters.
- ``geo.resolve`` — validate/expand a location UUID for address consumers
  (calendar/booking, listings).

Each carries a JSON schema in ``schemas/functions/``; the conftest runs
with ``VALIDATE_SCHEMAS`` on, so a payload drifting from its contract fails
loudly. Registration happens on import from ``apps.py:ready()``. Handlers
import the service layer lazily — importing this module needs no GDAL.
"""
import json
from pathlib import Path

from stapel_core.comm import function

_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas" / "functions"


def _schema(name: str) -> dict:
    return json.loads((_SCHEMAS_DIR / f"{name}.json").read_text(encoding="utf-8"))


@function("geo.nearby", schema=_schema("geo.nearby"))
def nearby_function(payload: dict) -> dict:
    """Proximity search by coordinates or geohash.

    Payload: ``{"lat": <num>, "lon": <num>}`` or ``{"geohash": "<str>"}``,
    plus optional ``precision`` (coords only) and ``limit``. Returns
    ``{"results": [{uuid, name, country, geohash, distance_km}, ...]}``
    nearest-first.
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


@function("geo.resolve", schema=_schema("geo.resolve"))
def resolve_function(payload: dict) -> dict:
    """Resolve a location UUID to a summary (cross-service reference check).

    Payload: ``{"uuid": "<uuid>"}``. Returns ``{"found": bool, "uuid": ...}``
    and, when found, ``name``/``country``/``type``/``display_name``.
    """
    from . import services

    return services.resolve(payload["uuid"])


__all__ = ["nearby_function", "resolve_function"]
