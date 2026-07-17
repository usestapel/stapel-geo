# Changelog

All notable changes to stapel-geo are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 semver: **minor = breaking**, patch = compatible.

## [0.3.2] — 2026-07-17

Fleet follow-up to stapel-core 0.12.0 (legacy shim sweep). No source
changes needed. Full suite green against core 0.12.0.

### Changed
- `stapel-core` dependency ceiling `<0.12` → `<0.13`.

## [0.3.1] — 2026-07-17

### Changed
- `stapel-core` ceiling raised `>=0.10,<0.11` → `>=0.10,<0.12` (core 0.11
  fleet re-pin: default bus, nav, config-checks, error params/language —
  additive for modules). Suite green as-is (incl. the `redis` extra).

## [0.3.0] — 2026-07-16

Geo v2 (geo-v2-redesign.md §63, owner directive): the module is now exactly
"geohash proximity search + a generic geocoder facade" — **no GDAL, no
PostGIS, no spatial database, ever**. Breaking release; alpha policy applies
(drop & rebuild, no data migration path).

### ⚠️ Removed (the PostGIS/GADM tail — gone as a class)
- **`Location.geometry`** (`MultiPolygonField`) and **`Location.center`**
  (`PointField`) — administrative boundary polygons and spatial
  `ST_Contains`-style queries are no longer a feature of this module.
- **`GeoFile` model + the whole GADM import machinery**: `imports.py`
  (`GeoFileImporter`, `ImportStatus`, `parse_geojson`), `import_feature`,
  `_get_property`/`_get_parent`, the `geo.import.completed` comm Action and
  its emit schema, the GADM import HTTP surface (`GeoFileViewSet`, retry).
- **`fast_centroid` and all polygon-simplification code**
  (`_simplify_polygon`, `_decimate_ring`, `_antimeridian_safe_centroid`,
  `_crosses_antimeridian`, `_shift_polygon`/`_shift_ring`) — that
  antimeridian machinery existed only for GADM polygons, not points.
- **Management commands** `enable_postgis` and `load_geofiles`; the
  `geofiles/` folder (flattening helper + GADM instructions).
- **`GeoModelAdminMixin`** spatial admin widget.
- **Packaging**: the `spatial` extra and the `GDAL>=3.0` dependency; the
  `stapel_geo.management` packages. CI no longer installs
  gdal-bin/libgdal/SpatiaLite — the whole suite runs on SQLite, and the
  25 GDAL skips-with-reason are gone as a class (149 passed / 0 skipped).
- **Location fields dropped with GADM**: `g_id`, `varname`, `iso_code`,
  `hasc_code`, `geo_file` FK.
- Settings dropped: `SIMPLIFY_MAX_POINTS`, `GADM_FOLDER`, `IMPORT_ASYNC`.
- Lazy exports dropped: `GeoFileImporter`, `ImportStatus`.

### ⚠️ Migration note (breaking)
- **Migrations were rebuilt from scratch** (alpha drop & rebuild):
  `migrations/0001_initial.py` is regenerated for the flat schema. There is
  no ALTER path from 0.2.x — drop the old `geo_*` tables and migrate fresh.
- **`Location` is now a flat point**: new `lat`/`lon` (`FloatField`,
  indexed) replace `center`; `geohash` is auto-encoded from them in
  `save()`. The treenode hierarchy (country -> region -> city), `uuid`
  cross-service reference and display names remain.
- **HTTP canon `/geo/api/v1/...`** (api-versioning.md): the host mount
  `path("geo/", include("stapel_geo.urls"))` now yields
  `/geo/api/v1/locations/...` and `/geo/api/v1/geocoding/...` — the old
  unversioned `/geo/api/...` paths are gone (no bare-path alias, per the
  owner's clean-slate ruling).
- **`STAPEL_GEO["GEOCODER"]` changed form**: a provider **name** from the
  merge-registry (`"photon"`, default) instead of a dotted path. Custom
  providers register via `STAPEL_GEO["GEOCODERS"] = {"name": "dotted.path"}`
  or `register_geocoder()`.
- **`Location` fills by hand or future flat CSV import** — GADM (heavy,
  non-commercial license) left with the polygon layer; a GeoNames-style
  management command is a separate task when demand is real.

### Added
- **Search facade** (`stapel_geo.search`): `GeoSearchBackend` protocol
  (`nearby` / `radius` / `bbox`), swapped by
  `STAPEL_GEO["SEARCH_BACKEND"]` (REPLACE semantics, §61 media pattern).
  Hits are `(location uuid, distance_km)` pairs — engine-agnostic keys the
  service layer joins back to rows.
  - `PostgresGeoSearchBackend` (default, zero new infra): the proven
    9-cell geohash neighbour machinery behind the facade; `radius()` picks
    its starting cell size from `pygeohash.PRECISION_TO_ERROR` and filters
    by exact haversine (membership, not top-K); `bbox()` is a flat indexed
    `lat/lon BETWEEN` with the lon range split in two across the
    antimeridian (`min_lon > max_lon`).
  - `RedisGeoSearchBackend` (first scale backend, `pip install
    stapel-geo[redis]`): `GEOADD`/`GEOSEARCH` side index (Redis is already
    mandatory house infra), synced via `post_save`/`post_delete` receivers
    when configured; the primary DB stays the source of truth;
    `rebuild()` re-indexes.
  - `ElasticsearchGeoSearchBackend` / `SolrGeoSearchBackend` stubs —
    `NotImplementedError` with implementation pointers.
- **comm Functions** `geo.radius`, `geo.bbox` and `geo.geohash_encode`
  (pure lat/lon -> geohash so consumers like listings stamp their own
  rows without importing geo), with JSON schemas; `geo.nearby`/`geo.radius`/
  `geo.bbox` all route through the facade — one code path per verb.
- **Geocoder provider merge-registry** (`BUILTIN_GEOCODERS` +
  `STAPEL_GEO["GEOCODERS"]` + `register_geocoder()`, the stapel-agent
  PROVIDERS pattern): `photon` (real, production default), `nominatim`
  (real: public OSM API, keyless, self-enforced 1 rps politeness +
  User-Agent — dev/fallback only), `google` / `yandex` (key-gated stubs;
  hosts bring their own PAYG keys, stapel never bundles them).
- **GeocodeCache ledger table**: one row per proxied geocoding call
  (`provider`/`verb`/`status`/`duration_ms`) — spend visibility per
  provider, the PromptLog pattern — doubling as the default cache storage
  (`GEOCODE_CACHE_POLICY` seam, `LedgerCachePolicy`, 30-day TTL).
- **Geocoder throttle**: DRF `ScopedRateThrottle` (scope `"geocoding"`),
  rate from `STAPEL_GEO["GEOCODER_THROTTLE"]` (default `30/min`) — a
  public endpoint cannot burn a metered upstream key unboundedly.
- **Flows** (`geo.location_browse` / `geo.location_nearby` /
  `geo.location_resolve` / `geo.geocode_address`) and the per-module
  contract triad harness (`make contract` -> committed
  `docs/{schema,flows,errors}.json` at the canonical `/geo/api/v1/`).
- System checks `stapel_geo.W003`/`W004` for `SEARCH_BACKEND`;
  `W001`/`W002` reworked for the name-based geocoder registry.

### Fixed
- `schemas/functions/geo.nearby.json` description still claimed
  `distance_km` is "an approximate geohash distance" — stale since the
  0.2.0 haversine fix; it now documents the exact great-circle distance.
- HTTP views use `StapelResponse` throughout and every documented endpoint
  belongs to a flow (`stapel-verify`: 0 errors, 0 warnings).

## [0.2.1] — Unreleased

### Changed
- Pinned `stapel-core` to the `>=0.8,<0.9` window (library-standard §7.1: one
  minor window; floor `0.8.0` is published on PyPI — no pin into the void).
- CI: added the release-track job (library-standard §7.4) — installs the package
  the way an end user does (`pip install .`, dependencies resolved from PyPI
  strictly by the declared pins, no git-main core, no editable siblings), asserts
  `stapel-core` resolves inside the `0.8` window, and runs an import smoke.
  Advisory (continue-on-error) until the whole stapel graph is on PyPI; becomes
  the blocking precondition for a `vX.Y.Z` tag once it is.

### Packaging
- Tests excluded from the built wheel/sdist (the `stapel_geo.tests`
  subpackage is no longer listed in `[tool.setuptools] packages`). Added
  `[project.urls]`, completed the trove classifiers (MIT/OSI, Python 3.13,
  `Typing :: Typed`, OS Independent, `3 :: Only`, Development Status) and a
  `[tool.ruff]` lint section (single source shared with the git hooks/CI).


## [0.2.0] — Unreleased

Correctness pass on geohash proximity, centroids and HTTP input validation
(internal adversarial code-review). **Breaking:** `nearby` distances change
(see migration note) and a geohash helper was renamed.

### ⚠️ Migration note (breaking)
- **`distance_km` is now a true haversine distance, not a prefix bucket.**
  The `distance_km` field returned by `geo.nearby` (comm) and the
  `nearby-by-*` HTTP endpoints previously reported `pygeohash`'s bucketed
  approximation — e.g. 22 m across the antimeridian came back as `20000.0`,
  and 1.1 km and 11.1 km both came back as `19.55`. It now returns the real
  great-circle distance in km. Consumers that compared against those bucket
  values (radius filters in `listings`) must recalibrate their thresholds.
- **`geohash.approximate_distance_km` was renamed to `geohash.distance_km`.**
  Internal helper; update any direct importers.

### Fixed
- **`nearby` lost the true nearest across a cell boundary** (`geohash.py`,
  H1). Prefix-only widening never looked at adjacent geohash cells, could
  stop as soon as it had `limit` candidates, and never did a final full scan
  — so it returned a 1334 km decoy over a 2.3 km neighbour across the
  antimeridian, a 500 km decoy over a 22 m neighbour across the equator, and
  returned **empty** near the poles / antimeridian (no shared prefix). Now
  each level queries the target cell **and its 8 neighbours**, trusts an
  early result only when the neighbour block was complete (no pole/seam gap
  where `pygeohash` cannot compute a neighbour) and the k-th candidate lies
  within that level's coverage radius, and otherwise falls back to an
  authoritative empty-prefix scan.
- **`fast_centroid` promoted a hole to the shell** (`models.py`, H2). When
  the exterior ring decimated below 4 points, `_simplify_polygon` dropped it
  and used a surviving hole as the exterior, landing the centroid *inside*
  the hole (measured 87.6 km off). The exterior ring is now preserved as the
  exterior; if it would collapse under decimation the polygon is left
  unsimplified. Collapsed holes are still dropped (documented, minor shift).
- **Antimeridian multipolygons centroided into the wrong ocean**
  (`models.py`, M2). A country split across ±180° (Fiji, Chukotka, NZ) got a
  planar centroid near longitude 0. Longitudes are now shifted into a
  continuous frame before the centroid and wrapped back, so the centroid
  (and its stored geohash) lands on the islands.
- **Geocoder proxy 500'd on colliding query params** (`geocoding/views.py`,
  M3). A user param named like a provider-method argument (`?query=…`,
  `?self=…`, reverse `?lng=…`) was forwarded as a kwarg and raised
  `TypeError`. Those names are now reserved and dropped. `limit` is coerced
  and clamped so an oversized value cannot provoke an upstream 4xx later
  masked as a 502.
- **Retrying a failed/stuck GeoFile never re-ran the import** (`models.py` /
  `views.py`, M4). The async trigger only fired for brand-new rows, so retry
  left the file `pending` forever. New `GeoFile.restart_import()` explicitly
  (re)starts the import (async or sync per `IMPORT_ASYNC`).
- **GADM import was not atomic** (`imports.py`, M5). A file failing mid-way
  left the locations imported before the bad feature committed behind a
  `failed` status. The feature loop now runs inside a transaction (injected
  `atomic`; the status machine stays DB-free by default), so a failure rolls
  the whole file back.
- **HTTP views 500'd on malformed input** (`views.py`, M6). Out-of-range or
  NaN/inf `lat`/`lon`, non-numeric `precision`/`limit`, and a non-UUID
  non-integer lookup now return `400`/`404` (and `validate-uuid` returns
  `valid: false`) instead of `500`.
- **Import robustness** (`models.py` / `management`, L1–L3). A feature missing
  its `GID_x` now raises a clean validation error instead of a raw
  `IntegrityError`; imported `Location`s record their source `geo_file`; and
  `load_geofiles --force` clears prior `GeoFile` rows first so repeated runs
  no longer accumulate duplicates.

## [0.1.0] — Unreleased

Initial port of the location + geocoding domain from the legacy geo module
into a standalone Stapel L2 module.

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

### Changed (provenance — how this differs from the legacy geo module)
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
