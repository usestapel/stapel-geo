"""System checks for the GEOCODER registry and SEARCH_BACKEND seams
(W-level — degradable)."""
from django.test import override_settings

from stapel_geo.checks import (
    check_basemap,
    check_geocoder,
    check_geocoder_languages,
    check_search_backend,
)


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


class TestGeocoderLanguageCheck:
    """W005/W006 — the deploy-time half of the "asked ru, got en" defect.

    The library cannot make Photon's index carry a language it was not
    built with. What it CAN do is stop that fact from being invisible:
    the clamp is silent by nature, so the checks say it out loud once,
    at deploy, with the exact command that fixes it.
    """

    def test_stock_english_site_on_stock_dump_is_quiet(self):
        # LANGUAGE_CODE defaults to en-us and "en" IS in the prebuilt
        # dumps — no warning, or the check would be noise everywhere.
        assert check_geocoder_languages(None) == []

    @override_settings(LANGUAGE_CODE="ru-ru")
    def test_a_russian_site_on_a_stock_dump_warns_w006(self):
        result = check_geocoder_languages(None)
        assert [warning.id for warning in result] == ["stapel_geo.W006"]
        # The remediation must be actionable, not "check your config".
        assert "-languages ru" in result[0].hint

    @override_settings(
        LANGUAGE_CODE="ru-ru",
        STAPEL_GEO={"PHOTON_LANGUAGES": ["default", "en", "ru"]},
    )
    def test_an_index_that_carries_the_language_is_quiet(self):
        assert check_geocoder_languages(None) == []

    @override_settings(STAPEL_GEO={"PHOTON_LANGUAGE_FALLBACK": "ru"})
    def test_a_fallback_the_index_lacks_warns_w005(self):
        # Clamping to a language Photon rejects turns every unsupported
        # request into a 502 instead of a degraded answer.
        result = check_geocoder_languages(None)
        assert "stapel_geo.W005" in [warning.id for warning in result]

    @override_settings(
        STAPEL_GEO={"GEOCODERS": {"fake": "stapel_geo.tests.fakes.FakeGeocoder"},
                    "GEOCODER": "fake"},
        LANGUAGE_CODE="ru-ru",
    )
    def test_a_non_photon_provider_is_not_lectured_about_photon(self):
        assert check_geocoder_languages(None) == []


class TestBasemapCheck:
    def test_debug_deployments_may_use_the_public_tiles(self):
        with override_settings(DEBUG=True):
            assert check_basemap(None) == []

    def test_public_osm_tiles_in_production_warn_w007(self):
        with override_settings(DEBUG=False):
            result = check_basemap(None)
        assert [warning.id for warning in result] == ["stapel_geo.W007"]

    @override_settings(
        DEBUG=False,
        STAPEL_GEO={"MAP_TILE_URL": "https://tiles.example.com/{z}/{x}/{y}.png"},
    )
    def test_an_own_tile_server_is_quiet(self):
        assert check_basemap(None) == []
