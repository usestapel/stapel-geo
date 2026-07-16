"""Models of stapel-geo — flat, GDAL-free.

``Location`` is a plain point in a ``django-treenode`` hierarchy
(country -> region -> city): latitude/longitude floats plus an indexed
geohash of that point, auto-encoded on save. No geometry columns, no
spatial database, no GDAL — the PostGIS/GADM polygon layer was removed
in 0.3.0 (see CHANGELOG).

``GeocodeCache`` is the geocoder ledger: one row per proxied geocoding
call (accounting is not optional), doubling as the default cache storage
for :class:`stapel_geo.geocoding.cache.LedgerCachePolicy` — the same
pattern as ``stapel-agent``'s ``PromptLog``.

House rules (docs/library-standard.md §3.8): cross-service references are
UUID fields (``Location.uuid``); the geohash of each point is stored and
indexed for prefix-based proximity search.
"""
from __future__ import annotations

import uuid as uuid_lib

from django.db import models
from treenode.models import TreeNodeModel

from . import geohash as geohash_utils
from .conf import geo_settings


class Location(TreeNodeModel):
    """A place in the hierarchical location tree (country -> region -> ...).

    Backed by ``django-treenode``. ``uuid`` is the stable cross-service
    reference; ``lat``/``lon`` hold the point coordinate and ``geohash``
    (auto-encoded from them on save) powers prefix-based proximity search.
    """

    treenode_display_field = "display_name"

    uuid = models.UUIDField(
        default=uuid_lib.uuid4, editable=False, unique=True, db_index=True
    )
    name = models.CharField(max_length=100, null=True, blank=True)
    type = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=255, default="", blank=True)
    lat = models.FloatField(null=True, blank=True, db_index=True)
    lon = models.FloatField(null=True, blank=True, db_index=True)
    geohash = models.CharField(max_length=12, null=True, blank=True, db_index=True)
    display_name_narrow = models.CharField(max_length=255, blank=True, default="")
    display_name_broad = models.CharField(max_length=255, blank=True, default="")

    def _short_name(self, location) -> str:
        return location.name or ""

    def _compute_display_name_narrow(self) -> str:
        parent = self.get_parent()
        if not parent:
            return self.name or ""
        return f"{self._short_name(parent)} - {self.name or ''}"

    def _compute_display_name_broad(self) -> str:
        ancestors = list(self.get_ancestors())
        if not ancestors:
            return self.name or ""
        if len(ancestors) == 1:
            return f"{self._short_name(ancestors[0])} - {self.name or ''}"
        return f"{self._short_name(ancestors[0])} - {ancestors[1].name or ''}"

    def save(self, *args, **kwargs):
        if self.lat is not None and self.lon is not None:
            self.geohash = geohash_utils.encode(
                self.lat, self.lon, precision=geo_settings.GEOHASH_PRECISION
            )
        else:
            self.geohash = None
        self.display_name_narrow = self._compute_display_name_narrow()
        self.display_name_broad = self._compute_display_name_broad()
        super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.type} in {self.country})"

    def __str__(self):
        return self.display_name


class GeocodeCache(models.Model):
    """Geocoder ledger + default cache storage (one row per proxied call).

    Every call through the geocoder proxy writes a row — ``status`` is
    ``ok`` / ``error`` / ``cache_hit`` — so the host can see spend per
    provider/verb the same way ``PromptLog`` exposes LLM spend. Successful
    rows double as the cache: :class:`~stapel_geo.geocoding.cache.
    LedgerCachePolicy` answers lookups from the latest ``ok`` row within
    ``GEOCODE_CACHE_TTL_DAYS``.
    """

    class Status(models.TextChoices):
        OK = "ok", "OK"
        ERROR = "error", "Error"
        CACHE_HIT = "cache_hit", "Cache hit"

    provider = models.CharField(max_length=64)
    verb = models.CharField(max_length=32)
    query_hash = models.CharField(max_length=64, db_index=True)
    lang = models.CharField(max_length=16, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices)
    duration_ms = models.PositiveIntegerField(default=0)
    response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["provider", "verb", "query_hash", "lang", "-created_at"],
                name="geo_geocode_cache_lookup",
            ),
        ]

    def __str__(self):
        return f"{self.provider}.{self.verb} [{self.status}]"


__all__ = ["Location", "GeocodeCache"]
