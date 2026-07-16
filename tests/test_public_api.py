"""Package-level public API (PEP 562 lazy exports) and import hygiene."""
import os
import subprocess
import sys

import stapel_geo


class TestLazyExports:
    def test_all_declares_public_api(self):
        assert stapel_geo.__all__ == [
            "GeoSearchBackend",
            "GeocodeCachePolicy",
            "GeocodeResponse",
            "Geocoder",
            "GeocoderError",
            "NominatimGeocoder",
            "PhotonGeocoder",
            "PostgresGeoSearchBackend",
            "RedisGeoSearchBackend",
            "geo_settings",
            "get_backend",
            "register_geocoder",
            "registered_geocoders",
        ]

    def test_settings_resolve(self):
        from stapel_geo.conf import geo_settings

        assert stapel_geo.geo_settings is geo_settings

    def test_geocoder_seam_exports_resolve(self):
        from stapel_geo.geocoding.base import Geocoder
        from stapel_geo.geocoding.providers import NominatimGeocoder, PhotonGeocoder

        assert stapel_geo.Geocoder is Geocoder
        assert stapel_geo.PhotonGeocoder is PhotonGeocoder
        assert stapel_geo.NominatimGeocoder is NominatimGeocoder

    def test_search_facade_exports_resolve(self):
        from stapel_geo.search import get_backend
        from stapel_geo.search.postgres import PostgresGeoSearchBackend
        from stapel_geo.search.redis import RedisGeoSearchBackend

        assert stapel_geo.get_backend is get_backend
        assert stapel_geo.PostgresGeoSearchBackend is PostgresGeoSearchBackend
        assert stapel_geo.RedisGeoSearchBackend is RedisGeoSearchBackend

    def test_unknown_attribute_raises(self):
        try:
            stapel_geo.nonexistent_export
        except AttributeError as exc:
            assert "nonexistent_export" in str(exc)
        else:
            raise AssertionError("expected AttributeError")


class TestImportHygiene:
    def test_package_import_is_django_free(self):
        """`import stapel_geo` must not import Django nor need settings."""
        env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
        code = (
            "import sys\n"
            "import stapel_geo\n"
            'bad = [m for m in sys.modules if m == "django" or m.startswith("django.")]\n'
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

    def test_no_gdal_anywhere(self):
        """0.3.0: nothing in the package may pull GDAL/GeoDjango — ever."""
        code = (
            "import sys\n"
            "import stapel_geo.geohash\n"
            "import stapel_geo.geocoding.providers\n"
            "import stapel_geo.search.base\n"
            'bad = [m for m in sys.modules if m == "osgeo" or "contrib.gis" in m]\n'
            'assert not bad, f"GDAL pulled in: {bad}"\n'
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(sys.executable),
        )
        assert result.returncode == 0, result.stderr
