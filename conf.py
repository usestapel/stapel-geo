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
        # This is NOT a preference list: it is a statement of fact about the
        # index on disk. Photon rejects (HTTP 400) any other value instead of
        # degrading, so the provider clamps to PHOTON_LANGUAGE_FALLBACK below.
        # The prebuilt GraphHopper dumps carry exactly these four; a Russian
        # (or any non-en/de/fr) index has to be built with
        # `photon.jar import -languages <codes>` — see checks.W006.
        "PHOTON_LANGUAGES": ["default", "en", "de", "fr"],
        # What a requested language OUTSIDE PHOTON_LANGUAGES clamps to.
        # "default" is Photon's own local-name mode: it answers in the
        # language the place is named in on the map (Russian in Russia,
        # Greek in Greece), which is what a monolingual product wants and is
        # never worse than a hardcoded "en". Set to None to forward nothing
        # and let Photon apply its own -default-language.
        "PHOTON_LANGUAGE_FALLBACK": "default",
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
        # Throttle rate applied to ANONYMOUS callers of the geocoder proxy.
        # Only reachable when GEOCODER_PERMISSIONS is opened up (the default
        # permission refuses anonymous callers outright), which a public
        # search page needs; a metered upstream must still not be free.
        "GEOCODER_ANON_THROTTLE": "10/min",
        # Permission classes of the geocoder proxy views (dotted paths, ALL
        # must pass — DRF semantics). The default refuses anonymous callers:
        # geocoding burns a metered upstream. A public address search (a
        # storefront's search page, an unauthenticated composer) opens it:
        #   STAPEL_GEO = {"GEOCODER_PERMISSIONS": [
        #       "rest_framework.permissions.AllowAny"]}
        # and then GEOCODER_ANON_THROTTLE is what stands between the proxy
        # and a scraper.
        "GEOCODER_PERMISSIONS": [
            "stapel_core.django.api.permissions.IsNotAnonymousUser"
        ],
        # Geocode cache policy (dotted path). The default reads/writes the
        # GeocodeCache ledger table in the primary DB. TTL in days below.
        "GEOCODE_CACHE_POLICY": "stapel_geo.geocoding.cache.LedgerCachePolicy",
        "GEOCODE_CACHE_TTL_DAYS": 30,
        # ------------------------------------------------------------------
        # Address display (the line a picker shows back to the human)
        # ------------------------------------------------------------------
        # Dotted path to the display-line builder (REPLACE seam):
        # ``(GeocodeProperties) -> str``. Every geocoded feature carries the
        # result as ``properties.formatted`` so no product has to reassemble
        # name/street/housenumber/city/country for itself.
        "ADDRESS_FORMATTER": "stapel_geo.geocoding.format.format_address",
        # ISO-3166-1 alpha-2 codes whose postal convention puts the house
        # number BEFORE the street ("7 Tverskaya Street"). Everywhere else
        # the street comes first ("Тверская улица, 7", "Hauptstraße 7").
        "ADDRESS_HOUSENUMBER_FIRST_COUNTRIES": [
            "US", "CA", "GB", "IE", "AU", "NZ", "IN", "FR", "ZA",
            "SG", "MY", "HK", "PH", "IL", "TH",
        ],
        # Whether the display line carries the postcode (the components are
        # always in ``properties.postcode`` either way).
        "ADDRESS_INCLUDE_POSTCODE": False,
        # ------------------------------------------------------------------
        # Point-on-map resolution (the "detect my position" round trip)
        # ------------------------------------------------------------------
        # How many reverse-geocode candidates the resolve verb asks for; the
        # first is the pick, the rest are the "not this one?" alternatives.
        "RESOLVE_CANDIDATES": 5,
        # Cap on ``?nearest=`` (known Location rows returned beside the
        # address). 0 in the request means "don't touch the tree at all".
        "RESOLVE_NEAREST_MAX": 10,
        # ------------------------------------------------------------------
        # Basemap — what the point-on-map UI needs and must not invent
        # ------------------------------------------------------------------
        # Raster tile template. The default is the OSM Foundation's own tile
        # server, whose Tile Usage Policy forbids heavy/commercial use:
        # it is a DEVELOPMENT default, the same stance as the public
        # Nominatim provider. Production points this at its own tile server
        # or a paid provider — checks.W007 says so when DEBUG is off.
        "MAP_TILE_URL": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        # Subdomain shards for the template's optional {s} placeholder.
        "MAP_TILE_SUBDOMAINS": [],
        # Attribution is a LICENCE OBLIGATION, not decoration: ODbL requires
        # OpenStreetMap to be credited on every map that shows its data.
        # Both forms ship so a frontend can render either an HTML credit
        # line or a plain-text one (canvas, print, native).
        "MAP_TILE_ATTRIBUTION_HTML": (
            '&copy; <a href="https://www.openstreetmap.org/copyright" '
            'target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
        ),
        "MAP_TILE_ATTRIBUTION_TEXT": "© OpenStreetMap contributors",
        "MAP_TILE_POLICY_URL": "https://operations.osmfoundation.org/policies/tiles/",
        # Zoom envelope. PICKED_ZOOM is where the map settles once a place
        # has been chosen (street level); DEFAULT_ZOOM is the opening view.
        "MAP_MIN_ZOOM": 2,
        "MAP_MAX_ZOOM": 19,
        "MAP_DEFAULT_ZOOM": 13,
        "MAP_PICKED_ZOOM": 17,
        # Opening centre as [lat, lon]. None = the frontend has no opinion
        # to inherit: open on the browser position, or the whole world.
        "MAP_DEFAULT_CENTER": None,
        # Area the product operates in, as [min_lon, min_lat, max_lon,
        # max_lat] (GeoJSON/Photon order). When set it clamps the picker's
        # panning AND biases forward geocoding — a RU-only marketplace stops
        # offering a street in Ohio. None = worldwide.
        "MAP_BBOX": None,
        # Whether the default skin offers the browser's geolocation prompt.
        "MAP_GEOLOCATION": True,
        # Search-as-you-type discipline the picker must obey so one keystroke
        # is not one upstream call.
        "MAP_SEARCH_MIN_CHARS": 3,
        "MAP_SEARCH_DEBOUNCE_MS": 350,
    },
    import_strings=("SEARCH_BACKEND", "GEOCODE_CACHE_POLICY", "ADDRESS_FORMATTER"),
)

__all__ = ["geo_settings"]
