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
| GEOCODER | env | dotted path to a Geocoder subclass — the geocoder-provider seam (REPLACE). | no | stapel_geo.geocoding.providers.PhotonGeocoder |
| PHOTON_URL | env | base URL of the Photon instance the default provider proxies. | no | http://localhost:2322 |
| PHOTON_LANGUAGES | env | language codes the configured Photon bundle indexes (others fall back to English). | no | [default, en, de, fr] |
| GEOCODER_TIMEOUT | env | HTTP timeout (seconds) for outbound geocoder requests. | no | 10 |
| GEOHASH_PRECISION | env | geohash precision stored on Location.center (characters, 1-12). | no | 8 |
| NEARBY_PRECISION | env | default geohash precision for a nearby search on raw coordinates. | no | 6 |
| NEARBY_LIMIT | env | default result count for nearby queries. | no | 10 |
| NEARBY_MAX_LIMIT | env | maximum result count for nearby queries. | no | 50 |
| SIMPLIFY_MAX_POINTS | env | polygons above this point count are simplified before centroid computation. | no | 100 |
| GADM_FOLDER | env | folder the `load_geofiles` command scans for GADM extracts (data not shipped). | no | /app/geofiles |
| IMPORT_ASYNC | env | when True, GeoFile imports run in a background thread and emit `geo.import.completed`. | no | true |
