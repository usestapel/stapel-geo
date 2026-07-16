"""Proximity-search facade of stapel-geo (geo-v2-redesign.md §2.2).

One string key — ``STAPEL_GEO["SEARCH_BACKEND"]`` — swaps the whole search
engine behind the comm/HTTP surface (REPLACE semantics, the §61 media-
backend pattern). Callers never see which backend answered:

    from stapel_geo.search import get_backend
    hits = get_backend().nearby(49.61, 6.13, limit=10)

Backends implement :class:`stapel_geo.search.base.GeoSearchBackend`
(``nearby`` / ``radius`` / ``bbox``). Shipped:

- ``postgres.PostgresGeoSearchBackend`` — the default: geohash prefix
  expansion over the ``Location`` table in the primary DB, zero new infra.
- ``redis.RedisGeoSearchBackend`` — Redis ``GEOSEARCH`` side-index for the
  hot set; Postgres stays the source of truth.
- ``elasticsearch.ElasticsearchGeoSearchBackend`` /
  ``solr.SolrGeoSearchBackend`` — stubs with pointers, for the day mixed
  text+geo ranking at scale is a real demand.
"""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from ..conf import geo_settings
from .base import GeoSearchBackend

_VERBS = ("nearby", "radius", "bbox")


def get_backend() -> GeoSearchBackend:
    """Instantiate ``STAPEL_GEO["SEARCH_BACKEND"]`` (resolved dotted path).

    Raises :class:`~django.core.exceptions.ImproperlyConfigured` when the
    configured class does not expose the three facade verbs — callers
    surface this as a 5xx, ``checks.W003/W004`` surface it at deploy time.
    """
    backend_cls = geo_settings.SEARCH_BACKEND
    if not isinstance(backend_cls, type) or not all(
        callable(getattr(backend_cls, verb, None)) for verb in _VERBS
    ):
        raise ImproperlyConfigured(
            "STAPEL_GEO['SEARCH_BACKEND'] must point to a class implementing "
            f"the GeoSearchBackend protocol (nearby/radius/bbox), got {backend_cls!r}"
        )
    return backend_cls()


__all__ = ["GeoSearchBackend", "get_backend"]
