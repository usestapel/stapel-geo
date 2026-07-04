"""Spatial models for stapel-geo (GeoDjango — requires GDAL + a spatial DB).

This is the only module that imports ``django.contrib.gis`` / GDAL. Every
other layer (geohash math, geocoder seam, comm surface, conf, the import
status machine) is GDAL-free and importable without a spatial stack. When
``stapel_geo`` is in ``INSTALLED_APPS`` this module loads, so a spatial
backend (PostGIS in production, SpatiaLite for local/CI tests) is required.

House rules (docs/library-standard.md §3.8): cross-service references are
UUID fields (``Location.uuid``); the geohash of each centroid is stored and
indexed for prefix-based proximity search.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid as uuid_lib

from django.contrib.gis.db import models as gis_models
from django.contrib.gis.geos import (
    GEOSGeometry,
    LinearRing,
    MultiPolygon,
    Point,
    Polygon,
)
from django.db import connection, models
from treenode.models import TreeNodeModel

from . import geohash as geohash_utils
from .conf import geo_settings
from .imports import GeoFileImporter, ImportStatus, ImportValidationError

logger = logging.getLogger(__name__)


def fast_centroid(geom: GEOSGeometry, max_points: int | None = None) -> Point:
    """Centroid of *geom*, simplifying huge polygons first for performance.

    Polygons under ``2 * max_points`` coordinates use the exact centroid;
    larger ones are decimated (every Nth point) before the centroid is
    computed — a boundary's centroid barely moves under uniform decimation,
    but the cost drops sharply. ``max_points`` defaults to
    ``STAPEL_GEO["SIMPLIFY_MAX_POINTS"]``.
    """
    if max_points is None:
        max_points = geo_settings.SIMPLIFY_MAX_POINTS
    if geom.geom_type not in ("MultiPolygon", "Polygon"):
        return geom.centroid

    total_points = geom.num_coords
    if total_points <= max_points * 2:
        return geom.centroid

    step = max(2, total_points // max_points)
    if geom.geom_type == "Polygon":
        simplified = _simplify_polygon(geom, step)
    else:
        simplified = MultiPolygon([_simplify_polygon(poly, step) for poly in geom])
    return simplified.centroid


def _simplify_polygon(poly: Polygon, step: int) -> Polygon:
    """Decimate a polygon's rings by taking every *step*-th point."""
    simplified_rings = []
    for ring in [poly.exterior_ring] + list(poly[1:]):
        coords = list(ring.coords)
        simplified_coords = coords[::step]
        if simplified_coords[0] != simplified_coords[-1]:
            simplified_coords.append(simplified_coords[0])
        if len(simplified_coords) >= 4:
            simplified_rings.append(LinearRing(simplified_coords))
    if not simplified_rings:
        return poly
    return Polygon(simplified_rings[0], simplified_rings[1:] if len(simplified_rings) > 1 else [])


class GeoFile(models.Model):
    """An uploaded GADM GeoJSON extract and its import lifecycle.

    Has no geometry columns of its own — it lives here only because it
    drives geometry import. The status machine is in ``stapel_geo.imports``
    (GDAL-free); this model injects the GDAL feature importer and the
    ``geo.import.completed`` emitter.
    """

    geo_json = models.FileField()
    added = models.DateTimeField(auto_now_add=True)
    location_level = models.PositiveIntegerField(default=0)
    validation_result = models.TextField(blank=True, default="")

    import_status = models.CharField(
        max_length=20, choices=ImportStatus.choices, default=ImportStatus.PENDING
    )
    import_progress = models.PositiveIntegerField(default=0)
    import_total = models.PositiveIntegerField(default=0)
    import_error = models.TextField(blank=True, default="")

    def __str__(self):
        return str(self.geo_json.name)

    # --- glue for the GDAL-free status machine -------------------------

    def open_geojson(self):
        self.geo_json.seek(0)
        return self.geo_json

    def _importer(self) -> GeoFileImporter:
        return GeoFileImporter(
            self,
            feature_importer=import_feature,
            emit=self._emit_completed,
        )

    def _emit_completed(self, payload: dict) -> None:
        from .actions import emit_import_completed

        emit_import_completed(payload)

    def run_import(self) -> str:
        """Run the import in the current thread. Returns the terminal status."""
        return self._importer().run()

    @classmethod
    def create_and_import_sync(cls, **kwargs):
        """Create a GeoFile and import it synchronously (tests / commands)."""
        instance = cls(**kwargs)
        instance.import_status = ImportStatus.PENDING
        # Bypass the async trigger in save() for a deterministic import.
        super(GeoFile, instance).save()
        instance.run_import()
        return instance

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.import_status == ImportStatus.PENDING and geo_settings.IMPORT_ASYNC:
            self._start_async_import()

    def _start_async_import(self):
        thread = threading.Thread(target=self._threaded_import, daemon=True)
        thread.start()

    def _threaded_import(self):
        connection.close()  # fresh connection for this thread
        try:
            self.run_import()
        finally:
            connection.close()


class Location(TreeNodeModel):
    """A place in the hierarchical location tree (country -> region -> ...).

    Backed by ``django-treenode``; boundary geometry and centroid come from
    a GADM import. ``uuid`` is the stable cross-service reference; ``geohash``
    (of the centroid) powers prefix-based proximity search.
    """

    treenode_display_field = "display_name"

    uuid = models.UUIDField(
        default=uuid_lib.uuid4, editable=False, unique=True, db_index=True
    )
    g_id = models.CharField(max_length=64, unique=True, default="")
    name = models.CharField(max_length=100, null=True, blank=True)
    type = models.CharField(max_length=100, null=True, blank=True)
    varname = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, default="")
    geometry = gis_models.MultiPolygonField(null=True, blank=True)
    center = gis_models.PointField(null=True, blank=True)
    geohash = models.CharField(max_length=12, null=True, blank=True, db_index=True)
    iso_code = models.CharField(max_length=20, null=True, blank=True)
    hasc_code = models.CharField(max_length=20, null=True, blank=True)
    geo_file = models.ForeignKey(
        GeoFile, on_delete=models.SET_NULL, null=True, blank=True
    )
    display_name_narrow = models.CharField(max_length=255, blank=True, default="")
    display_name_broad = models.CharField(max_length=255, blank=True, default="")

    def _short_name(self, location) -> str:
        return location.varname or location.name or ""

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
        if self.center:
            self.geohash = geohash_utils.encode(
                self.center.y, self.center.x, precision=geo_settings.GEOHASH_PRECISION
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


# --- GADM feature import (GDAL) ----------------------------------------


def _get_property(level: int, props: dict, prop_name: str):
    if level == 0:
        if prop_name == "NAME":
            return props.get("COUNTRY")
        if prop_name == "TYPE":
            return "Country"
    if prop_name == "COUNTRY":
        return props.get("COUNTRY")
    prop = props.get(f"{prop_name}_{level}")
    if prop == "NA" and prop_name != "NAME":
        return None
    return prop


def _get_parent(child_level: int, props: dict):
    if child_level == 0:
        return None
    level = child_level - 1
    location, created = Location.objects.get_or_create(
        g_id=props.get(f"GID_{level}"),
        defaults={"name": _get_property(level, props, "NAME")},
    )
    if created:
        location.set_parent(_get_parent(level, props))
    return location


def import_feature(location_level: int, feature: dict) -> None:
    """Upsert one GADM feature into a Location (GDAL geometry parsing).

    Injected into :class:`stapel_geo.imports.GeoFileImporter` as the
    ``feature_importer`` — the status machine calls it per feature.
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry")
    if not geometry:
        raise ImportValidationError("feature geometry is missing")

    geom_obj = GEOSGeometry(json.dumps(geometry))
    if geom_obj.geom_type != "MultiPolygon":
        raise ImportValidationError("feature geometry should be a MultiPolygon")

    location, created = Location.objects.update_or_create(
        g_id=props.get(f"GID_{location_level}"),
        defaults={
            "name": _get_property(location_level, props, "NAME"),
            "varname": _get_property(location_level, props, "VARNAME"),
            "country": _get_property(location_level, props, "COUNTRY") or "",
            "type": _get_property(location_level, props, "TYPE"),
            "iso_code": _get_property(location_level, props, "ISO"),
            "hasc_code": _get_property(location_level, props, "HASC"),
            "geometry": geom_obj,
            "center": fast_centroid(geom_obj),
        },
    )
    if created:
        location.set_parent(_get_parent(location_level, props))


__all__ = [
    "GeoFile",
    "Location",
    "fast_centroid",
    "import_feature",
    "ImportStatus",
]
