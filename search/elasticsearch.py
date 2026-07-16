"""Elasticsearch backend stub — the next scale candidate after Redis.

Elasticsearch is the right engine when the demand is **mixed text + geo
relevance ranking on a large corpus** (the legacy marketplace's ad-search
plan hit exactly this wall). Until that demand is real, this stays a stub:
implementing it means an index synced from the primary DB and the
``geo_distance`` / ``geo_bounding_box`` / ``geo_grid`` query DSL —
see https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-geo-queries
"""
from __future__ import annotations

_HINT = (
    "ElasticsearchGeoSearchBackend is a stub. Implement it against the ES "
    "geo queries (geo_distance for nearby/radius, geo_bounding_box for "
    "bbox, geo_grid for cell aggregation) with an index synced from the "
    "Location table, then point STAPEL_GEO['SEARCH_BACKEND'] at your class."
)


class ElasticsearchGeoSearchBackend:
    """Not implemented — a pointer, not a promise (geo-v2-redesign.md §2.2)."""

    def nearby(self, lat, lon, *, limit, precision=None):
        raise NotImplementedError(_HINT)

    def radius(self, lat, lon, radius_km, *, limit=None):
        raise NotImplementedError(_HINT)

    def bbox(self, min_lat, min_lon, max_lat, max_lon, *, limit=None):
        raise NotImplementedError(_HINT)


__all__ = ["ElasticsearchGeoSearchBackend"]
