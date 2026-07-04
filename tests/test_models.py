"""Spatial tests — the location tree, geohash-on-save, fast_centroid, GADM import.

These require a working GDAL/GEOS stack and a spatial DB; when that is
unavailable they are skipped WITH A REASON (see tests/_support.py), never
silently dropped. Run them in CI with GDAL + SpatiaLite/PostGIS.
"""
from pathlib import Path

import pytest

from stapel_geo.tests._support import requires_spatial

pytestmark = [requires_spatial, pytest.mark.django_db]

_SAMPLE = Path(__file__).resolve().parent.parent / "geofiles" / "gadm41_LUX_0.json"


class TestFastCentroid:
    def test_centroid_of_square(self):
        from django.contrib.gis.geos import Polygon

        from stapel_geo.models import fast_centroid

        square = Polygon(((0, 0), (0, 2), (2, 2), (2, 0), (0, 0)))
        centroid = fast_centroid(square)
        assert round(centroid.x, 6) == 1.0
        assert round(centroid.y, 6) == 1.0

    def test_large_polygon_is_simplified(self):
        import math

        from django.contrib.gis.geos import Polygon

        from stapel_geo.models import fast_centroid

        ring = [
            (math.cos(t / 100 * 2 * math.pi), math.sin(t / 100 * 2 * math.pi))
            for t in range(300)
        ]
        ring.append(ring[0])
        circle = Polygon(ring)
        centroid = fast_centroid(circle, max_points=50)
        assert abs(centroid.x) < 0.1
        assert abs(centroid.y) < 0.1


class TestLocationGeohash:
    def test_geohash_computed_on_save(self):
        from django.contrib.gis.geos import Point

        from stapel_geo.models import Location

        loc = Location.objects.create(g_id="X.1", name="Test", center=Point(6.13, 49.61))
        assert loc.geohash
        assert len(loc.geohash) == 8


class TestGadmImport:
    def test_sample_country_imports(self):
        from django.core.files import File

        from stapel_geo.imports import ImportStatus
        from stapel_geo.models import GeoFile, Location

        with open(_SAMPLE, "rb") as fh:
            geofile = GeoFile.create_and_import_sync(geo_json=File(fh, name=_SAMPLE.name))

        assert geofile.import_status == ImportStatus.COMPLETED
        assert geofile.location_level == 0
        country = Location.objects.filter(tn_parent__isnull=True).first()
        assert country is not None
        assert country.geohash
