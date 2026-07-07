"""comm Functions geo.nearby / geo.resolve — schema-validated, in-process.

The ORM query helpers in ``stapel_geo.services`` are monkeypatched so these
run without GDAL or a spatial DB, while the geohash ranking and the schema
contracts are exercised for real.
"""
import pytest
from stapel_core.comm import call
from stapel_core.comm.exceptions import SchemaValidationError

from stapel_geo import geohash, services
from stapel_geo.tests.fakes import NearbyCandidate


@pytest.fixture
def fake_locations(monkeypatch):
    """A tiny geohash-tagged pool behind services._fetch_prefix."""
    near = NearbyCandidate("uuid-near", "Near", "TL", geohash.encode(49.6112, 6.1302, 8))
    far = NearbyCandidate("uuid-far", "Far", "TL", geohash.encode(48.0, 2.0, 8))
    pool = [near, far]
    monkeypatch.setattr(services, "_fetch_prefix", lambda prefix: pool)
    return pool


class TestNearbyFunction:
    def test_nearby_by_coords_ranks_nearest_first(self, fake_locations):
        result = call("geo.nearby", {"lat": 49.611, "lon": 6.130, "limit": 2})
        names = [r["name"] for r in result["results"]]
        assert names[0] == "Near"
        assert result["results"][0]["distance_km"] is not None

    def test_nearby_by_geohash(self, fake_locations):
        gh = geohash.encode(49.611, 6.130, 8)
        result = call("geo.nearby", {"geohash": gh})
        assert result["results"][0]["uuid"] == "uuid-near"

    def test_summary_shape(self, fake_locations):
        row = call("geo.nearby", {"lat": 49.611, "lon": 6.130})["results"][0]
        assert set(row) == {"uuid", "name", "country", "geohash", "distance_km"}


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


class TestResolveFunction:
    def test_resolve_found(self, monkeypatch):
        loc = NearbyCandidate("uuid-1", "Testland", "Testland", "u0v9", type="Country")
        monkeypatch.setattr(services, "_get_location_by_uuid", lambda u: loc)
        result = call("geo.resolve", {"uuid": "uuid-1"})
        assert result["found"] is True
        assert result["name"] == "Testland"
        assert result["type"] == "Country"
        assert result["display_name"] == "Testland (Country in Testland)"

    def test_resolve_missing_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(services, "_get_location_by_uuid", lambda u: None)
        result = call("geo.resolve", {"uuid": "does-not-exist"})
        assert result == {"found": False, "uuid": "does-not-exist"}

    def test_resolve_requires_uuid(self):
        with pytest.raises(SchemaValidationError):
            call("geo.resolve", {})
