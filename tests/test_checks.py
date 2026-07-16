"""System checks for the GEOCODER registry and SEARCH_BACKEND seams
(W-level — degradable)."""
from django.test import override_settings

from stapel_geo.checks import check_geocoder, check_search_backend


class TestGeocoderCheck:
    def test_default_geocoder_is_ok(self):
        assert check_geocoder(None) == []

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"fake": "stapel_geo.tests.fakes.FakeGeocoder"},
                    "GEOCODER": "fake"}
    )
    def test_valid_registered_subclass_is_ok(self):
        assert check_geocoder(None) == []

    @override_settings(STAPEL_GEO={"GEOCODER": "not-registered"})
    def test_unknown_name_warns_w001(self):
        result = check_geocoder(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W001"

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"broken": "stapel_geo.does.not.Exist"},
                    "GEOCODER": "broken"}
    )
    def test_unimportable_entry_warns_w001(self):
        result = check_geocoder(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W001"

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"bad": "stapel_geo.tests.fakes.NotAGeocoder"},
                    "GEOCODER": "bad"}
    )
    def test_non_geocoder_warns_w002(self):
        result = check_geocoder(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W002"


class TestSearchBackendCheck:
    def test_default_backend_is_ok(self):
        assert check_search_backend(None) == []

    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.does.not.Exist"})
    def test_unimportable_path_warns_w003(self):
        result = check_search_backend(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W003"

    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.tests.fakes.NotASearchBackend"})
    def test_non_backend_warns_w004(self):
        result = check_search_backend(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W004"
