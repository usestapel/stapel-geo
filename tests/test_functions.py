"""comm Functions geo.nearby / geo.radius / geo.bbox / geo.geohash_encode /
geo.resolve — schema-validated, in-process, through the search facade."""
import pytest
from stapel_core.comm import call
from stapel_core.comm.exceptions import SchemaValidationError

from stapel_geo import geohash
from stapel_geo.models import Location

pytestmark = pytest.mark.django_db


@pytest.fixture
def locations():
    near = Location.objects.create(name="Near", country="TL", lat=49.6112, lon=6.1302)
    far = Location.objects.create(name="Far", country="TL", lat=48.0, lon=2.0)
    return {"near": near, "far": far}


class TestNearbyFunction:
    def test_nearby_by_coords_ranks_nearest_first(self, locations):
        result = call("geo.nearby", {"lat": 49.611, "lon": 6.130, "limit": 2})
        names = [r["name"] for r in result["results"]]
        assert names[0] == "Near"
        assert result["results"][0]["distance_km"] is not None

    def test_nearby_by_geohash(self, locations):
        gh = geohash.encode(49.611, 6.130, 8)
        result = call("geo.nearby", {"geohash": gh})
        assert result["results"][0]["uuid"] == str(locations["near"].uuid)

    def test_summary_shape(self, locations):
        row = call("geo.nearby", {"lat": 49.611, "lon": 6.130})["results"][0]
        assert set(row) == {"uuid", "name", "country", "geohash", "distance_km"}

    def test_antimeridian_edge_survives_the_facade(self):
        near = Location.objects.create(name="near", lat=0.0, lon=-179.98)
        Location.objects.create(name="decoy", lat=0.0, lon=168.0)
        result = call("geo.nearby", {"lat": 0.0, "lon": 179.999, "limit": 1})
        assert result["results"][0]["uuid"] == str(near.uuid)


class TestNearbySchema:
    def test_requires_coords_or_geohash(self):
        with pytest.raises(SchemaValidationError):
            call("geo.nearby", {"limit": 5})

    def test_latitude_out_of_range_is_rejected(self):
        with pytest.raises(SchemaValidationError):
            call("geo.nearby", {"lat": 200, "lon": 6.1})

    def test_extra_key_is_rejected(self):
        with pytest.raises(SchemaValidationError):
            call("geo.nearby", {"geohash": "u0v90", "junk": 1})

    def test_bad_geohash_characters_rejected(self):
        with pytest.raises(SchemaValidationError):
            call("geo.nearby", {"geohash": "AIO!"})


class TestRadiusFunction:
    def test_membership_inside_circle(self, locations):
        result = call("geo.radius", {"lat": 49.611, "lon": 6.130, "radius_km": 5})
        uuids = [r["uuid"] for r in result["results"]]
        assert uuids == [str(locations["near"].uuid)]
        assert result["results"][0]["distance_km"] <= 5

    def test_radius_must_be_positive(self):
        with pytest.raises(SchemaValidationError):
            call("geo.radius", {"lat": 0, "lon": 0, "radius_km": 0})

    def test_requires_radius(self):
        with pytest.raises(SchemaValidationError):
            call("geo.radius", {"lat": 0, "lon": 0})


class TestBboxFunction:
    def test_plain_box(self, locations):
        result = call("geo.bbox", {
            "min_lat": 49.0, "min_lon": 5.0, "max_lat": 50.0, "max_lon": 7.0,
        })
        uuids = [r["uuid"] for r in result["results"]]
        assert uuids == [str(locations["near"].uuid)]
        assert result["results"][0]["distance_km"] is None

    def test_antimeridian_box(self):
        east = Location.objects.create(name="east", lat=0.0, lon=179.5)
        west = Location.objects.create(name="west", lat=0.0, lon=-179.5)
        Location.objects.create(name="out", lat=0.0, lon=0.0)
        result = call("geo.bbox", {
            "min_lat": -1, "min_lon": 179.0, "max_lat": 1, "max_lon": -179.0,
        })
        uuids = {r["uuid"] for r in result["results"]}
        assert uuids == {str(east.uuid), str(west.uuid)}

    def test_requires_all_corners(self):
        with pytest.raises(SchemaValidationError):
            call("geo.bbox", {"min_lat": 0, "min_lon": 0, "max_lat": 1})


class TestGeohashEncodeFunction:
    def test_encodes_at_default_precision(self):
        result = call("geo.geohash_encode", {"lat": 49.6116, "lon": 6.1319})
        assert result["geohash"] == geohash.encode(49.6116, 6.1319, 8)

    def test_explicit_precision(self):
        result = call("geo.geohash_encode", {"lat": 49.6116, "lon": 6.1319, "precision": 5})
        assert len(result["geohash"]) == 5

    def test_requires_both_coordinates(self):
        with pytest.raises(SchemaValidationError):
            call("geo.geohash_encode", {"lat": 49.6})

    def test_out_of_range_rejected(self):
        with pytest.raises(SchemaValidationError):
            call("geo.geohash_encode", {"lat": 91, "lon": 0})


class TestResolveFunction:
    def test_resolve_found(self):
        loc = Location.objects.create(name="Testland", country="Testland", type="Country")
        result = call("geo.resolve", {"uuid": str(loc.uuid)})
        assert result["found"] is True
        assert result["name"] == "Testland"
        assert result["type"] == "Country"
        assert result["display_name"] == "Testland (Country in Testland)"

    def test_resolve_missing_is_not_an_error(self):
        missing = "00000000-0000-0000-0000-000000000000"
        result = call("geo.resolve", {"uuid": missing})
        assert result == {"found": False, "uuid": missing}

    def test_resolve_requires_uuid(self):
        with pytest.raises(SchemaValidationError):
            call("geo.resolve", {})
