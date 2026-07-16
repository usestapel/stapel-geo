"""Flat Location model + GeocodeCache ledger — no GDAL, plain SQLite."""
import pytest

from stapel_geo.models import GeocodeCache, Location

pytestmark = pytest.mark.django_db


class TestLocationGeohash:
    def test_save_encodes_geohash_from_lat_lon(self):
        loc = Location.objects.create(name="Luxembourg", lat=49.6116, lon=6.1319)
        assert loc.geohash
        assert len(loc.geohash) == 8  # GEOHASH_PRECISION default
        assert loc.geohash.startswith("u0u6")  # Luxembourg City cell

    def test_save_without_coords_clears_geohash(self):
        loc = Location.objects.create(name="Nowhere")
        assert loc.geohash is None

    def test_coords_update_reencodes_geohash(self):
        loc = Location.objects.create(name="Moving", lat=0.0, lon=0.0)
        first = loc.geohash
        loc.lat, loc.lon = 51.5, -0.12
        loc.save()
        assert loc.geohash != first

    def test_clearing_coords_clears_geohash(self):
        loc = Location.objects.create(name="Gone", lat=1.0, lon=1.0)
        loc.lat = None
        loc.save()
        assert loc.geohash is None


class TestLocationTree:
    def test_display_names_from_hierarchy(self):
        country = Location.objects.create(name="Testland", type="Country")
        region = Location.objects.create(name="Northland", type="Region")
        region.set_parent(country)
        region.save()
        city = Location.objects.create(name="Springfield", type="City")
        city.set_parent(region)
        city.save()
        assert city.display_name_narrow == "Northland - Springfield"
        assert city.display_name_broad == "Testland - Northland"
        assert country.display_name_narrow == "Testland"

    def test_display_name_property(self):
        loc = Location(name="Berlin", type="City", country="Germany")
        assert loc.display_name == "Berlin (City in Germany)"

    def test_uuid_is_unique_cross_service_reference(self):
        a = Location.objects.create(name="A")
        b = Location.objects.create(name="B")
        assert a.uuid != b.uuid


class TestGeocodeCacheLedger:
    def test_ledger_row_shape(self):
        row = GeocodeCache.objects.create(
            provider="photon",
            verb="search",
            query_hash="a" * 64,
            lang="en",
            status=GeocodeCache.Status.OK,
            duration_ms=42,
            response={"type": "FeatureCollection", "features": []},
        )
        assert str(row) == "photon.search [ok]"

    def test_statuses(self):
        assert set(GeocodeCache.Status.values) == {"ok", "error", "cache_hit"}
