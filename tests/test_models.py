"""Spatial tests — the location tree, geohash-on-save, fast_centroid, GADM import.

These require a working GDAL/GEOS stack and a spatial DB; when that is
unavailable they are skipped WITH A REASON (see tests/_support.py), never
silently dropped. Run them in CI with GDAL + SpatiaLite/PostGIS.
"""
from pathlib import Path

import pytest
from django.test import override_settings

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


class TestFastCentroidEdges:
    def test_hole_never_promoted_to_shell(self):
        # H2: a 5-point square shell that collapses under decimation, around a
        # dense 400-point hole. The old code dropped the shell and used the
        # hole as the exterior, landing the centroid *inside* the hole
        # (87.6 km off). The exterior must stay the exterior.
        import math

        from django.contrib.gis.geos import Point, Polygon

        from stapel_geo.models import fast_centroid

        shell = [(9, 49), (9, 51), (11, 51), (11, 49), (9, 49)]
        hole = [
            (10.6 + 0.35 * math.cos(2 * math.pi * i / 400),
             50.6 + 0.35 * math.sin(2 * math.pi * i / 400))
            for i in range(400)
        ]
        hole.append(hole[0])
        poly = Polygon(shell, hole)
        exact = poly.centroid
        fast = fast_centroid(poly)  # default SIMPLIFY_MAX_POINTS=100 -> decimates

        assert fast.distance(exact) < 0.05           # ~ matches the true centroid
        assert Point(10.6, 50.6).distance(fast) > 0.35  # outside the (dropped) hole

    def test_simplify_polygon_preserves_exterior_role(self):
        from django.contrib.gis.geos import Polygon

        from stapel_geo.models import _simplify_polygon

        shell = [(9, 49), (9, 51), (11, 51), (11, 49), (9, 49)]  # collapses at step 4
        hole = [(10.4, 50.4), (10.4, 50.8), (10.8, 50.8), (10.8, 50.4), (10.4, 50.4)]
        poly = Polygon(shell, hole)
        simplified = _simplify_polygon(poly, step=4)
        # exterior stays the big square, not the small hole
        assert simplified.exterior_ring.envelope.area > 3.0

    def test_antimeridian_multipolygon_centroid_lands_on_seam(self):
        # M2: a two-island country straddling +/-180 (Fiji-class). The planar
        # centroid of the parts lands near longitude 0 (Atlantic); normalized
        # it must sit on the antimeridian near the islands.
        from django.contrib.gis.geos import MultiPolygon, Polygon

        from stapel_geo.models import fast_centroid

        west = Polygon(((179.0, -18), (179.0, -16), (180.0, -16), (180.0, -18), (179.0, -18)))
        east = Polygon(((-180.0, -18), (-180.0, -16), (-179.0, -16),
                        (-179.0, -18), (-180.0, -18)))
        centroid = fast_centroid(MultiPolygon(west, east))

        assert abs(abs(centroid.x) - 180) < 2.0   # near +/-180, not near 0
        assert abs(centroid.y - (-17.0)) < 0.5


class TestImportValidation:
    def test_missing_gid_raises_validation_error(self):
        # L1: a feature without its GID is a clean validation error, not a raw
        # IntegrityError bubbling out of the DB.
        from stapel_geo.imports import ImportValidationError
        from stapel_geo.models import import_feature

        feature = {
            "properties": {"COUNTRY": "Nowhere"},
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        }
        with pytest.raises(ImportValidationError, match="GID_0"):
            import_feature(0, feature)


def _square_multipolygon(x, y):
    return {
        "type": "MultiPolygon",
        "coordinates": [[[[x, y], [x, y + 1], [x + 1, y + 1], [x + 1, y], [x, y]]]],
    }


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
        # L2: imported locations are traceable back to their source GeoFile.
        assert country.geo_file_id == geofile.id

    def test_import_is_atomic_on_failure(self):
        # M5: a file that fails mid-import leaves no partially imported
        # locations behind — the whole file rolls back.
        import json

        from django.core.files.base import ContentFile

        from stapel_geo.imports import ImportStatus
        from stapel_geo.models import GeoFile, Location

        collection = {
            "name": "gadm41_TST_0",
            "type": "FeatureCollection",
            "features": [
                {"properties": {"GID_0": "AAA", "COUNTRY": "Aaa"},
                 "geometry": _square_multipolygon(0, 0)},
                {"properties": {"GID_0": "BBB", "COUNTRY": "Bbb"}, "geometry": None},
            ],
        }
        payload = ContentFile(json.dumps(collection).encode(), name="tst.json")
        geofile = GeoFile.create_and_import_sync(geo_json=payload)

        assert geofile.import_status == ImportStatus.FAILED
        assert Location.objects.count() == 0  # AAA rolled back with BBB's failure

    @override_settings(STAPEL_GEO={"IMPORT_ASYNC": False})
    def test_retry_reruns_the_import(self):
        # M4: retrying a stuck/failed GeoFile actually re-runs the import
        # (previously the async trigger only fired for brand-new rows).
        from django.core.files import File

        from stapel_geo.imports import ImportStatus
        from stapel_geo.models import GeoFile, Location

        with open(_SAMPLE, "rb") as fh:
            geofile = GeoFile.objects.create(geo_json=File(fh, name=_SAMPLE.name))
        # ASYNC off => create() did not import; simulate a prior failure.
        assert not Location.objects.exists()
        geofile.import_status = ImportStatus.FAILED
        geofile.save()

        geofile.restart_import()

        geofile.refresh_from_db()
        assert geofile.import_status == ImportStatus.COMPLETED
        assert Location.objects.exists()
