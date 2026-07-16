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
| PHOTON_LANGUAGES | env | language codes the configured Photon bundle indexes (others fall back to English). | no | [default, en, de, fr] |
| NOMINATIM_URL | env | base URL for the "nominatim" provider (public instance: 1 rps, dev/fallback only). | no | https://nominatim.openstreetmap.org |
| GEOCODER_TIMEOUT | env | HTTP timeout (seconds) for outbound geocoder requests. | no | 10 |
| GEOCODER_THROTTLE | env | DRF scoped throttle rate (scope "geocoding") for the geocoder proxy views. | no | 30/min |
| GEOCODE_CACHE_POLICY | env | dotted path to the GeocodeCachePolicy subclass (REPLACE seam). | no | stapel_geo.geocoding.cache.LedgerCachePolicy |
| GEOCODE_CACHE_TTL_DAYS | env | TTL (days) for the default ledger-backed geocode cache. | no | 30 |
