"""Settings namespace resolution (STAPEL_GEO)."""
from django.test import override_settings

from stapel_geo.conf import geo_settings
from stapel_geo.search.postgres import PostgresGeoSearchBackend


class TestDefaults:
    def test_geocoder_default_is_the_photon_name(self):
        # 0.3.0: GEOCODER is a registry NAME, not a dotted path.
        assert geo_settings.GEOCODER == "photon"

    def test_search_backend_default_is_postgres_class(self):
        assert geo_settings.SEARCH_BACKEND is PostgresGeoSearchBackend

    def test_scalar_defaults(self):
        assert geo_settings.GEOHASH_PRECISION == 8
        assert geo_settings.NEARBY_PRECISION == 6
        assert geo_settings.NEARBY_MAX_LIMIT == 50
        assert geo_settings.GEOCODE_CACHE_TTL_DAYS == 30
        assert "en" in geo_settings.PHOTON_LANGUAGES

    def test_cache_policy_default_resolves(self):
        from stapel_geo.geocoding.cache import LedgerCachePolicy

        assert geo_settings.GEOCODE_CACHE_POLICY is LedgerCachePolicy


class TestOverrides:
    @override_settings(STAPEL_GEO={"PHOTON_URL": "http://photon.example:2322"})
    def test_dict_setting_overrides_default(self):
        assert geo_settings.PHOTON_URL == "http://photon.example:2322"

    @override_settings(STAPEL_GEO={"NEARBY_LIMIT": 25})
    def test_scalar_override(self):
        assert geo_settings.NEARBY_LIMIT == 25

    @override_settings(STAPEL_GEO={"SEARCH_BACKEND": "stapel_geo.search.redis.RedisGeoSearchBackend"})
    def test_search_backend_dotted_path_is_imported(self):
        from stapel_geo.search.redis import RedisGeoSearchBackend

        assert geo_settings.SEARCH_BACKEND is RedisGeoSearchBackend

    @override_settings(STAPEL_GEO={"GEOCODER": "nominatim"})
    def test_geocoder_name_override(self):
        assert geo_settings.GEOCODER == "nominatim"
