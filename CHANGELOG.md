# Changelog

All notable changes to stapel-geo are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 semver: **minor = breaking**, patch = compatible.

## [0.1.0] — Unreleased

Initial port of the location + geocoding domain from `legacy-geo` into a
standalone Stapel L2 module.

### Added
- **Location tree** (`Location`, GeoDjango + `django-treenode`): GADM
  boundary geometry, `fast_centroid` polygon simplification, indexed
  centroid geohash, and a stable cross-service `uuid`.
- **GADM import**: `GeoFile` + `imports.GeoFileImporter` status machine
  (`pending → processing → completed/failed`, progress tracking) and the
  `enable_postgis` / `load_geofiles` management commands.
- **Initial spatial migration** (`migrations/0001_initial.py`): `GeoFile` +
  `Location` (SRID-4326 `MultiPolygonField`/`PointField`, indexed centroid
  geohash, unique `uuid`, treenode tree fields). Generated and verified in a
  Docker GDAL env; applies cleanly on SpatiaLite and PostGIS.
- **Geohash proximity** (`geohash.py`): pure prefix-expansion nearby search
  and approximate-distance ranking; HTTP `nearby-by-coords` /
  `nearby-by-geohash` endpoints.
- **Geocoder proxy** (`geocoding/`): forward / structured / reverse
  geocoding behind the swappable `Geocoder` provider seam
  (`STAPEL_GEO["GEOCODER"]`), JWT-guarded, normalized `GeocodeResponse`.
- **comm surface**: `geo.nearby` / `geo.resolve` Functions and the
  `geo.import.completed` Action, each with a JSON schema in `schemas/`.
- `STAPEL_GEO` settings namespace, `error.*` keys, and `stapel_geo.W001/W002`
  system checks for the geocoder seam.

### Changed (provenance — how this differs from `legacy-geo`)
- **Geocoder generalized to a provider seam.** The source hardcoded a Photon
  proxy (`PHOTON_URL`, inline `requests` calls in the views). It is now the
  `Geocoder` ABC (`search`/`reverse`/`structured` → `GeocodeResponse`) with
  `PhotonGeocoder` as the default; Nominatim/Google/etc. drop in via
  `STAPEL_GEO["GEOCODER"]` without forking.
- **GDAL-lazy structure.** Only the models/views/serializers/admin import
  GeoDjango; the geohash math, geocoder proxy, comm surface, conf and the
  GADM import status machine are GDAL-free and import without a spatial
  stack. `import stapel_geo` is Django-free and GDAL-free (PEP 562).
- **Configuration** moved from module-level `getattr(settings, …)` /
  `os.getenv` to the `STAPEL_GEO` conf namespace (no import-time freezing).
- **Errors** use the StapelError envelope + `register_service_errors`;
  cross-service coupling (`common.*`) replaced with `stapel_core`.
- **comm-by-name**: added `geo.nearby` / `geo.resolve` so listings and
  calendar/booking query proximity/addresses without importing geo; the
  async GADM import now emits `geo.import.completed`.
- Bulk GADM data is **no longer shipped** — only a tiny sample extract plus
  the flattening helper; hosts supply their own extracts (`GADM_FOLDER`).

### Fixed
- **Spatial-stack detection** (`tests/_support.py`): `HAS_GDAL` / `HAS_GEOS`
  were removed in Django 4.0, so the old probe always raised and the spatial
  suite skipped **even under a working GDAL/CI**. Now probes `gdal_version()` /
  `geos_version()` directly — spatial tests run where GDAL is present and still
  skip-with-reason where it is missing/broken.
- **Spatial test URLconf** (`tests/urls.py`): mounts the geocoder proxy at
  `geo/geocoding/` (matching the non-spatial URLconf and the geocoding HTTP
  tests) so those tests resolve in spatial mode too, not only under
  `api/geocoding/`.

### Notes
- No GDPR consumer: locations are reference data, not user PII.
- The initial **spatial migration is now committed** (`migrations/0001_initial.py`),
  generated and verified in a Docker GDAL environment. The test suite still
  builds its schema from model state via `MIGRATION_MODULES={"geo": None}`; the
  spatial suite skips-with-reason only where GDAL is genuinely unavailable.
- **CI spatial backend: SpatiaLite works** — the CI `libsqlite3-mod-spatialite`
  step registers geometry columns (`geo_location.geometry`/`center`, SRID 4326,
  spatial index enabled) and runs the full spatial suite in-memory. A real
  PostGIS service is not required for CI; the same migration also applies on
  `postgis/postgis`.
