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
    """True iff GDAL and GEOS can actually be loaded (not just importable).

    ``HAS_GDAL`` / ``HAS_GEOS`` were removed in Django 4.0, so we probe the
    C libraries directly by asking for their versions: on a present, working
    stack these return a version string; a missing or broken install (e.g. a
    dlopen failure) raises, which we treat as unavailable.
    """
    try:
        from django.contrib.gis.gdal import gdal_version
        from django.contrib.gis.geos.libgeos import geos_version

        gdal_version()
        geos_version()
        return True
    except Exception:
        # A broken install (e.g. dlopen failure) raises — treat as unavailable.
        return False


SPATIAL = spatial_available()

requires_spatial = pytest.mark.skipif(not SPATIAL, reason=_REASON)
