"""HTTP surface of the flat location API at the canonical /geo/api/v1/ mount.

Input validation (M6 heritage): malformed or out-of-range query params and
non-UUID lookups must resolve to 4xx (400/404), never a 500.
"""
import pytest

from stapel_geo.models import Location

pytestmark = pytest.mark.django_db

_LOC = "/geo/api/v1/locations"


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

    def test_nearby_returns_nearest_first_with_distance(self, api_client):
        near = Location.objects.create(name="Near", lat=49.6112, lon=6.1302)
        Location.objects.create(name="Far", lat=48.0, lon=2.0)
        resp = api_client.get(f"{_LOC}/nearby-by-coords?lat=49.611&lon=6.130")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["uuid"] == str(near.uuid)
        assert body[0]["distance_km"] is not None

    def test_nearby_by_geohash_returns_200(self, api_client):
        Location.objects.create(name="Near", lat=49.6112, lon=6.1302)
        resp = api_client.get(f"{_LOC}/nearby-by-geohash?geohash=u0u65x90")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestListValidation:
    def test_bad_limit_on_search_is_400(self, api_client):
        resp = api_client.get(f"{_LOC}?search=ber&limit=abc")
        assert resp.status_code == 400

    def test_short_search_lists_roots(self, api_client):
        root = Location.objects.create(name="Testland")
        child = Location.objects.create(name="Springfield")
        child.set_parent(root)
        child.save()
        resp = api_client.get(_LOC)
        assert resp.status_code == 200
        names = [row["name"] for row in resp.json()]
        assert names == ["Testland"]

    def test_search_filters_by_name(self, api_client):
        Location.objects.create(name="Berlin")
        Location.objects.create(name="Paris")
        resp = api_client.get(f"{_LOC}?search=ber")
        assert [row["name"] for row in resp.json()] == ["Berlin"]


class TestTreeEndpoints:
    def test_countries_lists_roots(self, api_client):
        Location.objects.create(name="Testland", type="Country")
        resp = api_client.get(f"{_LOC}/countries")
        assert resp.status_code == 200
        assert resp.json()[0]["name"] == "Testland"

    def test_by_parent_lists_children(self, api_client):
        root = Location.objects.create(name="Testland")
        child = Location.objects.create(name="Springfield")
        child.set_parent(root)
        child.save()
        resp = api_client.get(f"{_LOC}/by-parent/{root.pk}")
        assert resp.status_code == 200
        assert [row["name"] for row in resp.json()] == ["Springfield"]


class TestLookupValidation:
    def test_non_uuid_non_int_lookup_is_404(self, api_client):
        resp = api_client.get(f"{_LOC}/not-a-uuid/")
        assert resp.status_code == 404

    def test_lookup_by_uuid(self, api_client):
        loc = Location.objects.create(name="Berlin", lat=52.52, lon=13.40)
        resp = api_client.get(f"{_LOC}/{loc.uuid}/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Berlin"
        assert body["lat"] == 52.52
        assert "geometry" not in body  # the polygon era is over

    def test_validate_uuid_malformed_is_200_invalid(self, api_client):
        resp = api_client.get(f"{_LOC}/validate-uuid/not-a-uuid/")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_validate_uuid_known_is_valid(self, api_client):
        loc = Location.objects.create(name="Known")
        resp = api_client.get(f"{_LOC}/validate-uuid/{loc.uuid}/")
        assert resp.json()["valid"] is True
