"""System checks for the GEOCODER seam (W-level — degradable)."""
from django.test import override_settings

from stapel_geo.checks import check_geocoder


class TestGeocoderCheck:
    def test_default_geocoder_is_ok(self):
        assert check_geocoder(None) == []

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.FakeGeocoder"})
    def test_valid_subclass_is_ok(self):
        assert check_geocoder(None) == []

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.does.not.Exist"})
    def test_unimportable_path_warns_w001(self):
        result = check_geocoder(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W001"

    @override_settings(STAPEL_GEO={"GEOCODER": "stapel_geo.tests.fakes.NotAGeocoder"})
    def test_non_geocoder_warns_w002(self):
        result = check_geocoder(None)
        assert len(result) == 1
        assert result[0].id == "stapel_geo.W002"
