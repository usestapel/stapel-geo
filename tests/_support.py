"""Shared test support: detect whether a working GDAL/GEOS stack is present.

GeoDjango needs the GDAL and GEOS C libraries. When they are missing (or
broken — a common local situation), the spatial model/HTTP tests are
skipped *with a reason* rather than erroring or being silently dropped;
every GDAL-free layer (geohash math, geocoder seam, comm surface, conf,
import status machine) still runs.
"""
from __future__ import annotations

import pytest

_REASON = (
    "spatial stack unavailable: GeoDjango needs the GDAL + GEOS C libraries "
    "and a spatial DB (PostGIS/SpatiaLite). Run these in CI with GDAL installed."
)


def spatial_available() -> bool:
    """True iff GDAL and GEOS can actually be loaded (not just importable)."""
    try:
        from django.contrib.gis.gdal import HAS_GDAL
        from django.contrib.gis.geos import HAS_GEOS

        return bool(HAS_GDAL and HAS_GEOS)
    except Exception:
        # A broken install (e.g. dlopen failure) raises rather than
        # reporting HAS_GDAL=False — treat that as unavailable too.
        return False


SPATIAL = spatial_available()

requires_spatial = pytest.mark.skipif(not SPATIAL, reason=_REASON)
