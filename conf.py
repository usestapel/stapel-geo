"""Settings namespace for stapel-geo.

All configuration is read through ``geo_settings`` (lazily, at call time) —
never via module-level ``os.getenv`` (values would freeze at import).
Resolution order per key: ``settings.STAPEL_GEO`` dict -> flat Django
setting of the same name -> environment variable -> default below.

Dotted-path keys listed in ``import_strings`` are resolved with
``import_string`` — the fork-free escape hatch for swappable behavior:

- ``SEARCH_BACKEND`` — the proximity-search backend seam (REPLACE
  semantics, single strategy): any
  :class:`stapel_geo.search.base.GeoSearchBackend` implementation.
- ``GEOCODE_CACHE_POLICY`` — the geocode cache seam: any
  :class:`stapel_geo.geocoding.cache.GeocodeCachePolicy` subclass.

``GEOCODER`` is **a provider name** (MERGE-registry semantics), not a
dotted path: the name is resolved through ``registered_geocoders()``
(``BUILTIN_GEOCODERS`` <- ``GEOCODERS`` setting <- ``register_geocoder()``
runtime registrations). Point ``GEOCODERS`` at your own dotted paths to
add/replace providers without forking (see MODULE.md).

Importing this module never touches Django models — it is safe in tooling.
"""
from stapel_core.conf import AppSettings

geo_settings = AppSettings(
    "STAPEL_GEO",
    defaults={
        # ------------------------------------------------------------------
        # Proximity search
        # ------------------------------------------------------------------
        # Dotted path to the GeoSearchBackend implementation (REPLACE
        # semantics). Default: geohash prefix search over the Location table
        # in the primary database — no extra infrastructure. Alternatives:
        # stapel_geo.search.redis.RedisGeoSearchBackend (side-index, Redis
        # GEOSEARCH), stapel_geo.search.elasticsearch/solr (stubs).
        "SEARCH_BACKEND": "stapel_geo.search.postgres.PostgresGeoSearchBackend",
        # Redis backend: connection URL and the sorted-set key of the side
        # index. Only read when SEARCH_BACKEND is the Redis backend.
        "REDIS_URL": "redis://localhost:6379/0",
        "REDIS_GEO_KEY": "stapel:geo:locations",
        # Geohash precision stored on Location (characters, 1-12).
        "GEOHASH_PRECISION": 8,
        # Default geohash precision when a nearby search is handed raw
        # coordinates (coarser than storage precision — proximity, not id).
        "NEARBY_PRECISION": 6,
        # Default / maximum result counts for nearby/radius/bbox queries.
        "NEARBY_LIMIT": 10,
        "NEARBY_MAX_LIMIT": 50,
        # ------------------------------------------------------------------
        # Geocoding
        # ------------------------------------------------------------------
        # Name of the default geocoder provider (a key of
        # registered_geocoders(): builtin "photon"/"nominatim" or a name you
        # registered). NOTE 0.3.0 breaking: this was a dotted path before.
        "GEOCODER": "photon",
        # Merge-registry of extra providers: {"name": "dotted.path.Class"}.
        # Merged over BUILTIN_GEOCODERS; None/"" removes a builtin name.
        "GEOCODERS": {},
        # Base URL of the Photon instance the default provider proxies.
        "PHOTON_URL": "http://localhost:2322",
        # Language codes the configured Photon bundle actually indexes.
        # A requested language outside this set falls back to English.
        "PHOTON_LANGUAGES": ["default", "en", "de", "fr"],
        # Base URL of the Nominatim API used by the "nominatim" provider.
        # The default is the public OSM instance: 1 request/second policy,
        # dev/fallback use only — self-host for production traffic.
        "NOMINATIM_URL": "https://nominatim.openstreetmap.org",
        # HTTP timeout (seconds) for outbound geocoder requests.
        "GEOCODER_TIMEOUT": 10,
        # DRF throttle rate for the geocoder proxy views (ScopedRateThrottle
        # scope "geocoding") — PAYG discipline: a public endpoint must not be
        # able to burn a metered upstream key unboundedly.
        "GEOCODER_THROTTLE": "30/min",
        # Geocode cache policy (dotted path). The default reads/writes the
        # GeocodeCache ledger table in the primary DB. TTL in days below.
        "GEOCODE_CACHE_POLICY": "stapel_geo.geocoding.cache.LedgerCachePolicy",
        "GEOCODE_CACHE_TTL_DAYS": 30,
    },
    import_strings=("SEARCH_BACKEND", "GEOCODE_CACHE_POLICY"),
)

__all__ = ["geo_settings"]
