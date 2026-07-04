"""Settings namespace for stapel-geo.

All configuration is read through ``geo_settings`` (lazily, at call time) —
never via module-level ``os.getenv`` (values would freeze at import).
Resolution order per key: ``settings.STAPEL_GEO`` dict -> flat Django
setting of the same name -> environment variable -> default below.

Dotted-path keys listed in ``import_strings`` are resolved with
``import_string`` — the fork-free escape hatch for swappable behavior. Only
``GEOCODER`` is a seam here (single strategy, REPLACE semantics): point it
at any :class:`stapel_geo.geocoding.base.Geocoder` subclass.

Importing this module never touches GDAL/GeoDjango — it is safe in tooling
without a spatial stack.
"""
from stapel_core.conf import AppSettings

geo_settings = AppSettings(
    "STAPEL_GEO",
    defaults={
        # Dotted path to a stapel_geo.geocoding.base.Geocoder subclass —
        # the geocoder-provider seam (single strategy, REPLACE semantics).
        # Swap for Nominatim/Google/etc. without forking (see MODULE.md).
        "GEOCODER": "stapel_geo.geocoding.providers.PhotonGeocoder",
        # Base URL of the Photon instance the default provider proxies.
        "PHOTON_URL": "http://localhost:2322",
        # Language codes the configured Photon bundle actually indexes.
        # A requested language outside this set falls back to English.
        "PHOTON_LANGUAGES": ["default", "en", "de", "fr"],
        # HTTP timeout (seconds) for outbound geocoder requests.
        "GEOCODER_TIMEOUT": 10,
        # Geohash precision stored on Location.center (characters, 1-12).
        "GEOHASH_PRECISION": 8,
        # Default geohash precision when a nearby search is handed raw
        # coordinates (coarser than storage precision — proximity, not id).
        "NEARBY_PRECISION": 6,
        # Default / maximum result counts for nearby queries.
        "NEARBY_LIMIT": 10,
        "NEARBY_MAX_LIMIT": 50,
        # fast_centroid simplification budget: polygons with more than this
        # many points are simplified before the centroid is computed.
        "SIMPLIFY_MAX_POINTS": 100,
        # Folder the load_geofiles command scans for GADM extracts. Hosts
        # supply their own extracts here — data is NOT shipped (see MODULE.md).
        "GADM_FOLDER": "/app/geofiles",
        # When True, GeoFile imports run in a background thread and emit
        # ``geo.import.completed`` on success. When False, callers drive the
        # import synchronously (create_and_import_sync) — used in tests.
        "IMPORT_ASYNC": True,
    },
    import_strings=("GEOCODER",),
)

__all__ = ["geo_settings"]
