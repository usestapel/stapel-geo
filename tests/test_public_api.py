"""Package-level public API (PEP 562 lazy exports) and import hygiene."""
import os
import subprocess
import sys

import stapel_geo


class TestLazyExports:
    def test_all_declares_public_api(self):
        assert stapel_geo.__all__ == [
            "GeocodeResponse",
            "Geocoder",
            "GeocoderError",
            "GeoFileImporter",
            "ImportStatus",
            "PhotonGeocoder",
            "geo_settings",
        ]

    def test_settings_resolve(self):
        from stapel_geo.conf import geo_settings

        assert stapel_geo.geo_settings is geo_settings

    def test_geocoder_seam_exports_resolve(self):
        from stapel_geo.geocoding.base import Geocoder
        from stapel_geo.geocoding.providers import PhotonGeocoder

        assert stapel_geo.Geocoder is Geocoder
        assert stapel_geo.PhotonGeocoder is PhotonGeocoder

    def test_import_machine_exports_resolve(self):
        from stapel_geo.imports import GeoFileImporter, ImportStatus

        assert stapel_geo.ImportStatus is ImportStatus
        assert stapel_geo.GeoFileImporter is GeoFileImporter

    def test_unknown_attribute_raises(self):
        try:
            stapel_geo.nonexistent_export
        except AttributeError as exc:
            assert "nonexistent_export" in str(exc)
        else:
            raise AssertionError("expected AttributeError")


class TestImportHygiene:
    def test_package_import_is_django_and_gdal_free(self):
        """`import stapel_geo` must not import Django or GDAL nor need settings."""
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
        code = (
            "import sys\n"
            "import stapel_geo\n"
            'bad = [m for m in sys.modules if m == "django" or m.startswith("django.") '
            'or m == "osgeo" or "gdal" in m.lower()]\n'
            'assert not bad, f"heavy modules imported at package import time: {bad}"\n'
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=os.path.dirname(sys.executable),
        )
        assert result.returncode == 0, result.stderr

    def test_geohash_layer_imports_without_gdal(self):
        code = (
            "import sys\n"
            "import stapel_geo.geohash\n"
            "import stapel_geo.geocoding.providers\n"
            "import stapel_geo.imports\n"
            'bad = [m for m in sys.modules if m == "osgeo" or "contrib.gis" in m]\n'
            'assert not bad, f"GDAL pulled in by GDAL-free layers: {bad}"\n'
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(sys.executable),
        )
        assert result.returncode == 0, result.stderr
