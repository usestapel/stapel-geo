# CONFIG.MD — stapel-geo

Config registry for **stapel-geo** (`static-scaffold-and-config.md` §2). One row
per configuration key the module reads, its **source** (`env` = the process
environment / the `STAPEL_GEO` settings dict), what it is for, whether it is
required, and its default.

Every key is read through `geo_settings` (`stapel_geo.conf.AppSettings`,
namespace `STAPEL_GEO`). Resolution order per key: `settings.STAPEL_GEO` dict →
a flat Django setting of the same name → environment variable → the default
below.

## stapel-geo

| Key | Source | Purpose | Required | Default |
|-----|--------|---------|----------|---------|
| SEARCH_BACKEND | env | dotted path to the GeoSearchBackend implementation behind nearby/radius/bbox (REPLACE seam). | no | stapel_geo.search.postgres.PostgresGeoSearchBackend |
| REDIS_URL | env | Redis connection URL for the Redis search backend (only read when that backend is configured). | no | redis://localhost:6379/0 |
| REDIS_GEO_KEY | env | sorted-set key of the Redis geo side index. | no | stapel:geo:locations |
| GEOHASH_PRECISION | env | geohash precision stored on Location (characters, 1-12). | no | 8 |
| NEARBY_PRECISION | env | default geohash precision for a nearby search on raw coordinates. | no | 6 |
| NEARBY_LIMIT | env | default result count for nearby/radius/bbox queries. | no | 10 |
| NEARBY_MAX_LIMIT | env | maximum result count for nearby/radius/bbox queries. | no | 50 |
| GEOCODER | env | **name** of the default geocoder provider (a registered_geocoders() key; was a dotted path before 0.3.0). | no | photon |
| GEOCODERS | env | merge-registry of extra providers `{name: dotted_path}` over BUILTIN_GEOCODERS; None/"" removes a name. | no | {} |
| PHOTON_URL | env | base URL of the Photon instance the default provider proxies. | no | http://localhost:2322 |
| PHOTON_LANGUAGES | env | language codes the configured Photon bundle **actually indexes** — a statement of fact, not a preference: Photon answers HTTP 400 for anything else, so listing a language the index lacks makes every request a 502 (see checks.W005/W006). | no | [default, en, de, fr] |
| PHOTON_LANGUAGE_FALLBACK | env | what a language outside PHOTON_LANGUAGES clamps to. "default" is Photon's local-name mode (Russian in Russia); None forwards nothing. Before 0.4.0 this was hardcoded to "en", which returned English addresses to Russian products with no error. | no | default |
| NOMINATIM_URL | env | base URL for the "nominatim" provider (public instance: 1 rps, dev/fallback only). | no | https://nominatim.openstreetmap.org |
| GEOCODER_TIMEOUT | env | HTTP timeout (seconds) for outbound geocoder requests. | no | 10 |
| GEOCODER_THROTTLE | env | DRF scoped throttle rate (scope "geocoding") for identified callers of the geocoder proxy. | no | 30/min |
| GEOCODER_ANON_THROTTLE | env | throttle rate applied to anonymous callers; only reachable once GEOCODER_PERMISSIONS is opened up. | no | 10/min |
| GEOCODER_PERMISSIONS | env | permission classes (dotted paths, ALL must pass) of the four geocoder proxy verbs. Default refuses anonymous callers — geocoding burns a metered upstream. A public address-search page sets ["rest_framework.permissions.AllowAny"]. | no | [stapel_core.django.api.permissions.IsNotAnonymousUser] |
| GEOCODE_CACHE_POLICY | env | dotted path to the GeocodeCachePolicy subclass (REPLACE seam). | no | stapel_geo.geocoding.cache.LedgerCachePolicy |
| GEOCODE_CACHE_TTL_DAYS | env | TTL (days) for the default ledger-backed geocode cache. | no | 30 |
| ADDRESS_FORMATTER | env | dotted path to the display-line builder `(GeocodeProperties) -> str` (REPLACE seam); its result is `properties.formatted` on every feature. | no | stapel_geo.geocoding.format.format_address |
| ADDRESS_HOUSENUMBER_FIRST_COUNTRIES | env | ISO alpha-2 codes whose postal convention puts the house number before the street ("7 Tverskaya Street"); everywhere else the street leads. | no | [US, CA, GB, IE, AU, NZ, IN, FR, ZA, SG, MY, HK, PH, IL, TH] |
| ADDRESS_INCLUDE_POSTCODE | env | whether the display line carries the postcode (the component is always available regardless). | no | False |
| RESOLVE_CANDIDATES | env | reverse-geocode candidates the resolve verb asks for: the first is the pick, the rest are the "not this one?" alternatives. | no | 5 |
| RESOLVE_NEAREST_MAX | env | cap on `?nearest=` — how many known Location rows may accompany a resolved point (0 in the request = the tree is not queried). | no | 10 |
| MAP_TILE_URL | env | raster tile template for the picker. The default is the OSM Foundation's public server, whose Tile Usage Policy forbids heavy/commercial use — a DEVELOPMENT default (checks.W007). | no | https://tile.openstreetmap.org/{z}/{x}/{y}.png |
| MAP_TILE_SUBDOMAINS | env | shards for the template's optional {s} placeholder. | no | [] |
| MAP_TILE_ATTRIBUTION_HTML | env | credit line as HTML. A LICENCE OBLIGATION under ODbL, not decoration. | no | &copy; <a href="…">OpenStreetMap</a> contributors |
| MAP_TILE_ATTRIBUTION_TEXT | env | the same credit as plain text (canvas, print, native). | no | © OpenStreetMap contributors |
| MAP_TILE_POLICY_URL | env | the tile provider's usage policy, surfaced to the frontend. | no | https://operations.osmfoundation.org/policies/tiles/ |
| MAP_MIN_ZOOM | env | lowest zoom the layer serves. | no | 2 |
| MAP_MAX_ZOOM | env | highest zoom the layer serves. | no | 19 |
| MAP_DEFAULT_ZOOM | env | opening zoom of the picker. | no | 13 |
| MAP_PICKED_ZOOM | env | zoom the map settles on once a place is chosen. | no | 17 |
| MAP_DEFAULT_CENTER | env | opening centre as [lat, lon]; None = no opinion (open on the browser position, or the world). | no | None |
| MAP_BBOX | env | the product's operating area as [min_lon, min_lat, max_lon, max_lat]: clamps the picker AND becomes the default hard restriction on forward geocoding. None = worldwide. | no | None |
| MAP_GEOLOCATION | env | whether the default skin offers the browser's position prompt. | no | True |
| MAP_SEARCH_MIN_CHARS | env | characters before search-as-you-type fires. | no | 3 |
| MAP_SEARCH_DEBOUNCE_MS | env | idle time before a keystroke becomes an upstream request. | no | 350 |
