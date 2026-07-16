"""Redis ``GEOSEARCH`` backend — the first optional scale backend.

Redis solves the 9-cell geohash boundary problem natively (``GEOADD`` /
``GEOSEARCH`` operate on 52-bit geohash scores with engine-side neighbour
handling), and Redis is already mandatory house infrastructure
(``stapel_core.django.settings.get_default_cache`` configures it from
``REDIS_URL``) — so enabling this backend deploys zero new services.

The index is a **side index**: the primary DB (``Location`` rows) remains
the source of truth; ``post_save`` / ``post_delete`` signal receivers
(connected in ``apps.py:ready()`` only when this backend is configured)
keep the Redis sorted set in sync. Rebuild it any time with
:meth:`RedisGeoSearchBackend.rebuild`.

Members are ``str(Location.uuid)`` — the same hit keys every backend
returns. ``nearby``'s ``precision`` parameter is ignored (Redis picks its
own cell strategy).
"""
from __future__ import annotations

import logging
import math

from ..conf import geo_settings

logger = logging.getLogger(__name__)

# Half the Earth's circumference, km — a BYRADIUS that covers the planet,
# turning GEOSEARCH into a pure top-K nearest query for nearby().
_PLANET_RADIUS_KM = 20038.0

_KM_PER_DEG_LAT = 111.32


class RedisGeoSearchBackend:
    """``GEOADD``/``GEOSEARCH`` over a Redis side index (hot-set scale)."""

    def __init__(self, client=None):
        self._client = client

    # -- connection -----------------------------------------------------

    def client(self):
        """The redis-py client (lazily created from ``REDIS_URL``)."""
        if self._client is None:
            try:
                import redis
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "RedisGeoSearchBackend requires the 'redis' package "
                    "(pip install redis)"
                ) from exc
            self._client = redis.Redis.from_url(geo_settings.REDIS_URL)
        return self._client

    def _key(self) -> str:
        return geo_settings.REDIS_GEO_KEY

    # -- facade verbs ----------------------------------------------------

    def nearby(
        self, lat: float, lon: float, *, limit: int, precision: int | None = None
    ) -> list[tuple[str, float]]:
        if limit <= 0:
            return []
        return self._geosearch_radius(lat, lon, _PLANET_RADIUS_KM, count=limit)

    def radius(
        self, lat: float, lon: float, radius_km: float, *, limit: int | None = None
    ) -> list[tuple[str, float]]:
        return self._geosearch_radius(lat, lon, radius_km, count=limit)

    def bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        *,
        limit: int | None = None,
    ) -> list[str]:
        # GEOSEARCH BYBOX takes a center + width/height, which handles the
        # antimeridian for free: a min_lon > max_lon box is just a center on
        # the far side of ±180° with the wrapped longitude span as width.
        lon_span = (max_lon - min_lon) % 360 or (0 if min_lon == max_lon else 360)
        center_lat = (min_lat + max_lat) / 2
        center_lon = min_lon + lon_span / 2
        if center_lon > 180:
            center_lon -= 360
        height_km = max(0.1, (max_lat - min_lat) * _KM_PER_DEG_LAT)
        width_km = max(
            0.1, lon_span * _KM_PER_DEG_LAT * math.cos(math.radians(center_lat))
        )
        raw = self.client().geosearch(
            self._key(),
            longitude=center_lon,
            latitude=center_lat,
            width=width_km,
            height=height_km,
            unit="km",
            **({"count": limit} if limit is not None else {}),
        )
        return [self._decode(member) for member in raw]

    # -- side-index maintenance -------------------------------------------

    def index(self, location) -> None:
        """Upsert one Location into the side index (post_save receiver)."""
        if location.lat is None or location.lon is None:
            self.remove(str(location.uuid))
            return
        self.client().geoadd(
            self._key(), (location.lon, location.lat, str(location.uuid))
        )

    def remove(self, key: str) -> None:
        """Drop one member from the side index (post_delete receiver)."""
        self.client().zrem(self._key(), key)

    def rebuild(self) -> int:
        """Re-index every Location with coordinates; returns the count."""
        from ..models import Location

        client = self.client()
        client.delete(self._key())
        count = 0
        for loc in Location.objects.exclude(lat=None).exclude(lon=None).iterator():
            client.geoadd(self._key(), (loc.lon, loc.lat, str(loc.uuid)))
            count += 1
        return count

    # -- helpers -----------------------------------------------------------

    def _geosearch_radius(
        self, lat: float, lon: float, radius_km: float, *, count: int | None
    ) -> list[tuple[str, float]]:
        raw = self.client().geosearch(
            self._key(),
            longitude=lon,
            latitude=lat,
            radius=radius_km,
            unit="km",
            withdist=True,
            sort="ASC",
            **({"count": count} if count is not None else {}),
        )
        return [(self._decode(member), round(float(dist), 2)) for member, dist in raw]

    @staticmethod
    def _decode(member) -> str:
        return member.decode() if isinstance(member, bytes) else str(member)


def sync_location(sender, instance, **kwargs) -> None:
    """``post_save`` receiver: mirror the row into the Redis side index.

    Connected in ``apps.py:ready()`` only when the configured backend is
    Redis-based. Never breaks the save — the primary DB is the source of
    truth, a missed index write is recoverable via ``rebuild()``.
    """
    _sync(lambda backend: backend.index(instance))


def remove_location(sender, instance, **kwargs) -> None:
    """``post_delete`` receiver: drop the row from the Redis side index."""
    _sync(lambda backend: backend.remove(str(instance.uuid)))


def _sync(op) -> None:
    from . import get_backend

    try:
        backend = get_backend()
        if isinstance(backend, RedisGeoSearchBackend):
            op(backend)
    except Exception:  # noqa: BLE001 — the side index must never break saves
        logger.warning("Redis geo side-index sync failed", exc_info=True)


__all__ = ["RedisGeoSearchBackend", "sync_location", "remove_location"]
