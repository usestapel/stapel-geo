"""HTTP-layer input validation for the spatial views (M6).

Malformed or out-of-range query params and non-UUID lookups must resolve to
4xx (400/404), never a 500. Requires the spatial app + a spatial DB; skipped
with a reason when GDAL/GEOS is unavailable.
"""
import pytest

from stapel_geo.tests._support import requires_spatial

pytestmark = [requires_spatial, pytest.mark.django_db]

_LOC = "/geo/api/locations"


class TestNearbyValidation:
    @pytest.mark.parametrize("qs", [
        "lat=91&lon=0",       # latitude out of range
        "lat=-91&lon=0",
        "lat=0&lon=181",      # longitude out of range
        "lat=nan&lon=0",      # NaN
        "lat=inf&lon=0",      # infinity
        "lat=abc&lon=0",      # not a number
        "lat=0",              # missing lon
    ])
    def test_bad_coords_are_400_not_500(self, api_client, qs):
        resp = api_client.get(f"{_LOC}/nearby-by-coords?{qs}")
        assert resp.status_code == 400

    @pytest.mark.parametrize("qs", [
        "lat=0&lon=0&precision=abc",
        "lat=0&lon=0&limit=abc",
        "lat=0&lon=0&limit=1e3",
    ])
    def test_bad_precision_or_limit_is_400(self, api_client, qs):
        resp = api_client.get(f"{_LOC}/nearby-by-coords?{qs}")
        assert resp.status_code == 400

    def test_bad_limit_on_geohash_nearby_is_400(self, api_client):
        resp = api_client.get(f"{_LOC}/nearby-by-geohash?geohash=u0v90&limit=abc")
        assert resp.status_code == 400

    def test_valid_coords_return_200(self, api_client):
        resp = api_client.get(f"{_LOC}/nearby-by-coords?lat=49.6&lon=6.1")
        assert resp.status_code == 200


class TestListValidation:
    def test_bad_limit_on_search_is_400(self, api_client):
        resp = api_client.get(f"{_LOC}?search=ber&limit=abc")
        assert resp.status_code == 400


class TestLookupValidation:
    def test_non_uuid_non_int_lookup_is_404(self, api_client):
        resp = api_client.get(f"{_LOC}/not-a-uuid/")
        assert resp.status_code == 404

    def test_validate_uuid_malformed_is_200_invalid(self, api_client):
        resp = api_client.get(f"{_LOC}/validate-uuid/not-a-uuid/")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False
