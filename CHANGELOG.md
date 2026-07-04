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

### Notes
- No GDPR consumer: locations are reference data, not user PII.
- The initial **spatial migration is not committed** — it must be generated
  in a GDAL environment (`makemigrations geo`); tests build the schema from
  model state (`MIGRATION_MODULES`), and the spatial suite skips-with-reason
  where GDAL is unavailable.
