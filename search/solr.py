"""Solr backend stub.

Solr's spatial support (``LatLonPointSpatialField``, ``{!geofilt}`` /
``{!bbox}`` filters) is comparable to Elasticsearch for point queries and
stronger on polygon-buffer intersections, but there is no reason to pick
it first in 2026 — it exists here so a host already running Solr has a
named seam to fill. See https://solr.apache.org/guide/solr/latest/query-guide/spatial-search.html
"""
from __future__ import annotations

_HINT = (
    "SolrGeoSearchBackend is a stub. Implement it with Solr spatial search "
    "({!geofilt} for nearby/radius, {!bbox} for bbox over a "
    "LatLonPointSpatialField) synced from the Location table, then point "
    "STAPEL_GEO['SEARCH_BACKEND'] at your class."
)


class SolrGeoSearchBackend:
    """Not implemented — a pointer, not a promise (geo-v2-redesign.md §2.2)."""

    def nearby(self, lat, lon, *, limit, precision=None):
        raise NotImplementedError(_HINT)

    def radius(self, lat, lon, radius_km, *, limit=None):
        raise NotImplementedError(_HINT)

    def bbox(self, min_lat, min_lon, max_lat, max_lon, *, limit=None):
        raise NotImplementedError(_HINT)


__all__ = ["SolrGeoSearchBackend"]
