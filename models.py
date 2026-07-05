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
from functools import partial

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

    Polygons under ``2 * max_points`` coordinates use the full geometry;
    larger ones are decimated (every Nth point) before the centroid is
    computed — a boundary's centroid barely moves under uniform decimation,
    but the cost drops sharply. ``max_points`` defaults to
    ``STAPEL_GEO["SIMPLIFY_MAX_POINTS"]``.

    The centroid is computed antimeridian-aware (see
    :func:`_antimeridian_safe_centroid`) so archipelago countries straddling
    ±180° (Fiji, Chukotka, NZ) do not land in the wrong ocean.
    """
    if max_points is None:
        max_points = geo_settings.SIMPLIFY_MAX_POINTS
    if geom.geom_type not in ("MultiPolygon", "Polygon"):
        return geom.centroid

    total_points = geom.num_coords
    if total_points <= max_points * 2:
        simplified = geom
    else:
        step = max(2, total_points // max_points)
        if geom.geom_type == "Polygon":
            simplified = _simplify_polygon(geom, step)
        else:
            simplified = MultiPolygon([_simplify_polygon(poly, step) for poly in geom])
    return _antimeridian_safe_centroid(simplified)


def _decimate_ring(ring: LinearRing, step: int) -> LinearRing | None:
    """Take every *step*-th point of *ring*, re-closing it.

    Returns ``None`` when fewer than 4 distinct points survive (a ring needs
    4 coordinates including the repeated closing point) — the caller decides
    what a collapsed ring means for its role (exterior vs hole).
    """
    coords = list(ring.coords)
    simplified = coords[::step]
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    if len(simplified) < 4:
        return None
    return LinearRing(simplified)


def _simplify_polygon(poly: Polygon, step: int) -> Polygon:
    """Decimate a polygon's rings, preserving which ring is the exterior.

    The exterior ring is decimated as the exterior; a hole that collapses
    to fewer than 4 points is dropped. Crucially, if the *exterior* ring
    would collapse under decimation we return the polygon unsimplified —
    otherwise a surviving hole would be promoted to the shell and the
    centroid could land inside what used to be a hole.
    """
    exterior = _decimate_ring(poly.exterior_ring, step)
    if exterior is None:
        return poly
    holes = []
    for ring in poly[1:]:
        decimated = _decimate_ring(ring, step)
        if decimated is not None:
            holes.append(decimated)
    return Polygon(exterior, *holes)


def _polygon_lons(poly: Polygon):
    for ring in [poly.exterior_ring] + list(poly[1:]):
        for x, _y in ring.coords:
            yield x


def _crosses_antimeridian(geom: GEOSGeometry) -> bool:
    """True when *geom*'s longitude span exceeds 180° (antimeridian wrap).

    A single contiguous landmass never spans more than 180° of longitude,
    so a wider span means the geometry is split across ±180° and its planar
    (naive) centroid would be dragged toward longitude 0.
    """
    polys = [geom] if geom.geom_type == "Polygon" else list(geom)
    lons = [x for poly in polys for x in _polygon_lons(poly)]
    if not lons:
        return False
    return (max(lons) - min(lons)) > 180


def _shift_ring(ring: LinearRing) -> LinearRing:
    return LinearRing([(x + 360 if x < 0 else x, y) for x, y in ring.coords])


def _shift_polygon(poly: Polygon) -> Polygon:
    exterior = _shift_ring(poly.exterior_ring)
    holes = [_shift_ring(r) for r in poly[1:]]
    return Polygon(exterior, *holes)


def _antimeridian_safe_centroid(geom: GEOSGeometry) -> Point:
    """Centroid of *geom*, correct for geometries straddling ±180°.

    When the geometry crosses the antimeridian, western longitudes are
    shifted into a continuous ``[0, 360)`` frame before the centroid is
    taken, then the result is wrapped back into ``(-180, 180]``. Non-crossing
    geometries use the plain centroid unchanged.
    """
    if geom.geom_type not in ("MultiPolygon", "Polygon") or not _crosses_antimeridian(geom):
        return geom.centroid
    if geom.geom_type == "Polygon":
        shifted = _shift_polygon(geom)
    else:
        shifted = MultiPolygon([_shift_polygon(poly) for poly in geom])
    centre = shifted.centroid
    lon = centre.x
    if lon > 180:
        lon -= 360
    return Point(lon, centre.y, srid=geom.srid)


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
        from django.db import transaction

        return GeoFileImporter(
            self,
            feature_importer=partial(import_feature, geo_file=self),
            emit=self._emit_completed,
            atomic=transaction.atomic,
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

    def restart_import(self) -> None:
        """Reset an already-persisted GeoFile and re-run its import.

        The ``save()`` async trigger only fires for brand-new rows, so a retry
        (the row already has a pk) must kick the import off explicitly —
        otherwise the file would sit in ``pending`` forever. Honours
        ``IMPORT_ASYNC``: background thread when set, synchronous otherwise.
        """
        self.import_status = ImportStatus.PENDING
        self.import_progress = 0
        self.import_total = 0
        self.import_error = ""
        self.validation_result = ""
        self.save()  # existing row -> save() does not auto-trigger
        if geo_settings.IMPORT_ASYNC:
            self._start_async_import()
        else:
            self.run_import()

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


def import_feature(location_level: int, feature: dict, geo_file: "GeoFile | None" = None) -> None:
    """Upsert one GADM feature into a Location (GDAL geometry parsing).

    Injected into :class:`stapel_geo.imports.GeoFileImporter` as the
    ``feature_importer`` — the status machine calls it per feature. The model
    binds *geo_file* (the source :class:`GeoFile`) via ``functools.partial``
    so every imported Location is traceable back to its file.
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry")
    if not geometry:
        raise ImportValidationError("feature geometry is missing")

    g_id = props.get(f"GID_{location_level}")
    if not g_id:
        raise ImportValidationError(f"feature is missing GID_{location_level}")

    geom_obj = GEOSGeometry(json.dumps(geometry))
    if geom_obj.geom_type != "MultiPolygon":
        raise ImportValidationError("feature geometry should be a MultiPolygon")

    location, created = Location.objects.update_or_create(
        g_id=g_id,
        defaults={
            "name": _get_property(location_level, props, "NAME"),
            "varname": _get_property(location_level, props, "VARNAME"),
            "country": _get_property(location_level, props, "COUNTRY") or "",
            "type": _get_property(location_level, props, "TYPE"),
            "iso_code": _get_property(location_level, props, "ISO"),
            "hasc_code": _get_property(location_level, props, "HASC"),
            "geometry": geom_obj,
            "center": fast_centroid(geom_obj),
            "geo_file": geo_file,
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
