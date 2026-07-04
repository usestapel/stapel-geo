"""Settings namespace resolution (STAPEL_GEO)."""
from django.test import override_settings

from stapel_geo.conf import geo_settings
from stapel_geo.geocoding.providers import PhotonGeocoder


class TestDefaults:
    def test_geocoder_default_is_photon(self):
        assert geo_settings.GEOCODER is PhotonGeocoder

    def test_scalar_defaults(self):
        assert geo_settings.GEOHASH_PRECISION == 8
        assert geo_settings.NEARBY_PRECISION == 6
        assert geo_settings.NEARBY_MAX_LIMIT == 50
        assert "en" in geo_settings.PHOTON_LANGUAGES


class TestOverrides:
    @override_settings(STAPEL_GEO={"PHOTON_URL": "http://photon.example:2322"})
    def test_dict_setting_overrides_default(self):
        assert geo_settings.PHOTON_URL == "http://photon.example:2322"

    @override_settings(STAPEL_GEO={"NEARBY_LIMIT": 25})
    def test_scalar_override(self):
        assert geo_settings.NEARBY_LIMIT == 25

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_geocoder_dotted_path_is_imported(self):
        from stapel_geo.tests.fakes import FakeGeocoder

        assert geo_settings.GEOCODER is FakeGeocoder
