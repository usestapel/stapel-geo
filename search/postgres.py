"""Default search backend: geohash prefix expansion over the primary DB.

No new infrastructure — candidates come from an indexed
``geohash__startswith`` query on the ``Location`` table (any Django DB
backend, not only Postgres, despite the name: the primary relational
store is the source of truth).

- ``nearby`` is the proven 9-cell neighbour machinery from
  ``stapel_geo.geohash`` (equator / antimeridian / pole safe — see the
  edge tests) moved behind the facade.
- ``radius`` reuses the same neighbour block but picks the starting cell
  size from ``pygeohash.PRECISION_TO_ERROR`` (finest precision whose
  guaranteed cell radius still covers ``radius_km``) and filters by true
  haversine distance instead of taking top-K.
- ``bbox`` deliberately skips geohash cell-covering: a flat indexed
  ``lat BETWEEN / lon BETWEEN`` range is simpler and correct, with the
  ``lon`` range split in two when the box crosses the antimeridian
  (``min_lon > max_lon``).
"""
from __future__ import annotations

import pygeohash as pgh

from .. import geohash as geohash_utils
from ..conf import geo_settings

_CELL_ERROR_M = pgh.PRECISION_TO_ERROR


def _fetch_prefix(prefix: str) -> list:
    """Every Location whose stored geohash starts with *prefix* (ORM)."""
    from ..models import Location

    return list(Location.objects.filter(geohash__startswith=prefix))


def _radius_start_precision(radius_km: float) -> int:
    """Finest geohash precision whose cell error still covers *radius_km*.

    The 9-cell neighbour block at this precision provably contains every
    point within ``radius_km`` of the target (the block extends at least
    one full cell — >= the per-precision error radius — beyond the target
    cell in every direction). Falls back to precision 1 for planet-scale
    radii; the caller handles the incomplete-block case.
    """
    radius_m = radius_km * 1000
    candidates = [p for p, err in _CELL_ERROR_M.items() if 1 <= p <= 12 and err >= radius_m]
    return max(candidates) if candidates else 1


class PostgresGeoSearchBackend:
    """Geohash prefix search over the ``Location`` table (the default)."""

    def nearby(
        self, lat: float, lon: float, *, limit: int, precision: int | None = None
    ) -> list[tuple[str, float]]:
        precision = precision or geo_settings.NEARBY_PRECISION
        precision = max(1, min(12, precision))
        target = geohash_utils.encode(lat, lon, precision=precision)
        ranked = geohash_utils.nearby(target, _fetch_prefix, limit)
        return [(str(row.uuid), distance) for row, distance in ranked]

    def radius(
        self, lat: float, lon: float, radius_km: float, *, limit: int | None = None
    ) -> list[tuple[str, float]]:
        target = geohash_utils.encode(
            lat, lon, precision=geo_settings.GEOHASH_PRECISION
        )
        start = _radius_start_precision(radius_km)
        block, complete = geohash_utils._fetch_block(target[:start], _fetch_prefix)
        if not complete:
            # A pole/antimeridian gap in the neighbour block means it does
            # not actually cover the nominal radius — scan authoritatively.
            block = _fetch_prefix("")
        hits: list[tuple[str, float]] = []
        for row, distance in geohash_utils.rank_by_proximity(target, block):
            if distance is None or distance > radius_km:
                continue
            hits.append((str(row.uuid), distance))
            if limit is not None and len(hits) >= limit:
                break
        return hits

    def bbox(
        self,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        *,
        limit: int | None = None,
    ) -> list[str]:
        from django.db.models import Q

        from ..models import Location

        qs = Location.objects.filter(lat__gte=min_lat, lat__lte=max_lat)
        if min_lon <= max_lon:
            qs = qs.filter(lon__gte=min_lon, lon__lte=max_lon)
        else:
            # The box crosses the antimeridian: one logical range wraps into
            # two indexed ranges (lon >= min_lon OR lon <= max_lon).
            qs = qs.filter(Q(lon__gte=min_lon) | Q(lon__lte=max_lon))
        qs = qs.order_by("pk")
        if limit is not None:
            qs = qs[: max(0, limit)]
        return [str(u) for u in qs.values_list("uuid", flat=True)]


__all__ = ["PostgresGeoSearchBackend"]
