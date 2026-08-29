# Changelog

All notable changes to stapel-geo are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Pre-1.0 semver: **minor = breaking**, patch = compatible.

## [0.4.1] — 2026-08-30

### The need: the picker has to open somewhere before the user has said anything

0.4.0 shipped the map, the search, the address line and the confirmation
step — everything downstream of "where are you?". It left the very first
frame unanswered. A composer or a search page mounts, the browser's
geolocation prompt goes up, and the map has to be drawn *now*, before the
answer comes back and whether or not it ever does. **"Denied" is a
supported answer, not an error** — so are a dismissed prompt, an insecure
context, an old browser and a desktop with no radio, and in every one of
them a map still has to open. Opening on `{0, 0}` puts a seller in the
Gulf of Guinea; opening on a hardcoded capital is the same guess made
worse, because each product hardcodes a different one.

The server already holds the one fact that answers this without asking
anybody: the address the request arrived on.

### Added — `GET /geo/api/v1/ip`

- **The endpoint** (`ipgeo/`) answers an `IpLocation`: `lat`, `lon`,
  `source`, `precision`, `ip_resolved`, `label`, `city`, `region`,
  `country`, `country_code`, `accuracy_radius_km`. Public (`AllowAny`)
  and throttled (scope `geo_ip`) — the caller is a visitor with no
  account, which is the entire situation the verb exists for.
- **It always answers.** An unknown address, a broken database, a locator
  a deployment never configured: each comes back `200` with the fallback
  centre and `ip_resolved: false`. A map that cannot open is worse than a
  map that opens in the wrong city, and a frontend forced to branch on a
  4xx here would just hardcode a centre — which is the defect. The one
  non-200 is `204`, for a deployment with no locator answer **and** no
  fallback centre: an explicit refusal to have an opinion, told apart
  from a centre a caller should use.
- **It says how much it knows.** `source` / `precision` / `ip_resolved`
  are the difference between "we think you are in Moscow" and "we have no
  idea, here is where this site lives". A UI that shows the first as a
  confirmed address is lying to its user.
- **Locator seam** — `IpLocator` ABC (`locate(ip) -> IpLocation | None`)
  behind the same merge-registry the geocoders use: `IP_LOCATORS` ←
  `register_ip_locator()`, with `IP_LOCATOR` naming the default.
  Returning `None` means "I do not know" and is a **normal** answer (a
  private address, an unseeded range, a loopback request in development);
  `IpLocatorError` is for a genuinely broken backend, and the service
  logs it and falls back rather than 500ing.
- **Built-ins.** `maxmind` reads an **offline** MaxMind/GeoLite2 City
  `.mmdb` through the optional `geoip2` package (new extra
  `stapel-geo[ipgeo]`, path in `IP_MAXMIND_DB`, reader cached per path):
  no network call, no third party told who visits the site, nothing
  metered. No database is bundled — MaxMind requires an account to
  download GeoLite2 and forbids redistributing it, the same
  bring-your-own discipline the paid geocoders are under. `static`
  answers one configured point for everybody: not a placeholder, but the
  honest answer for a single-city marketplace, and better than a provider
  that is right about the country and wrong about the city.
- **A floor under both** — `IP_FALLBACK_CENTER`, or `MAP_DEFAULT_CENTER`
  when it is unset. The map's opening centre is already the deployment's
  answer to "where does this product live"; making a second setting
  mandatory to restate it is how the two drift apart.
- **Answers are cached per address** for `IP_CACHE_TTL_S` (default one
  hour) — an IP's city does not change between two page loads, and
  without it a storefront does a lookup per visitor per navigation.
  Negatives are cached too, but the fallback is applied **on read**, not
  stored, so moving `MAP_DEFAULT_CENTER` takes effect at once.
- `map/config`'s `endpoints` gained `"ip": "api/v1/ip"`, so a frontend
  learns the path from the server like the other four. The
  `geo.pick_location` flow gained the IP step at order 2.
- 28 tests (`tests/test_ipgeo.py`), including the forged-header cases.

### Added — which address the request came from

The half of this that is a security decision, not a lookup.
`X-Forwarded-For` is written by whoever is in front of you and **anyone
can send one**, so reading its leftmost entry — the idiom every snippet
on the internet shows — lets a caller pick their own IP by typing it.
For an endpoint that geolocates and throttles by address, that is the
whole ballgame.

So the default is `REMOTE_ADDR` and nothing else
(`IP_TRUSTED_PROXY_DEPTH = 0`), and trusting a header at all is an
explicit statement of topology: the depth is **how many hops the
deployment owns** — `1` behind one nginx, `2` behind nginx behind a CDN.
The chain considered is `X-Forwarded-For ++ [REMOTE_ADDR]` and the client
is read `depth` places from its **right** end, which is what makes a
forged prefix inert: a caller may prepend as many entries as they like
and none of them is ever the one that gets read. A topology the counter
does not describe replaces the whole function through
`IP_CLIENT_IP_RESOLVER` instead of accumulating header settings.

### Configuration

New `STAPEL_GEO` keys (full table in `CONFIG.MD`): `IP_LOCATOR`
(`"maxmind"`), `IP_LOCATORS` (`{}`), `IP_MAXMIND_DB` (`""`),
`IP_STATIC_POINT` / `IP_STATIC_LABEL` / `IP_STATIC_PRECISION`
(`None` / `""` / `"city"`), `IP_FALLBACK_CENTER` / `IP_FALLBACK_LABEL`
(`None` / `""`), `IP_TRUSTED_PROXY_DEPTH` (`0`), `IP_CLIENT_IP_RESOLVER`
(`stapel_geo.ipgeo.client_ip.client_ip_from_request`), `IP_PERMISSIONS`
(`[AllowAny]`), `IP_THROTTLE` / `IP_ANON_THROTTLE` (`120/min` /
`60/min`), `IP_CACHE_TTL_S` (`3600`). New extra: `stapel-geo[ipgeo]`
(and `[all]` now covers `redis,ipgeo`).

### Checks

- **`stapel_geo.W008`** — `IP_LOCATOR` names an unregistered locator, or
  its registry entry fails to import (the `geoip2` package is missing) or
  is not an `IpLocator`.
- **`stapel_geo.W009`** — the configured locator has nothing to answer
  with (no database, no static point) **and** no fallback centre exists,
  so the endpoint answers `204` to everybody. This is the failure that
  most needs saying out loud: an IP endpoint returning the default to
  every visitor looks exactly like one that is working.
- **`stapel_geo.W010`** — the site declares itself behind a proxy
  (`USE_X_FORWARDED_HOST` or `SECURE_PROXY_SSL_HEADER`) while
  `IP_TRUSTED_PROXY_DEPTH` is still `0`, so the address being geolocated
  is the proxy's and every visitor lands in the same city.

### What this is not

An IP is a **coarse** signal and this ships as one deliberately. It is
city-level at best where it is right at all; it is the exit node for
anyone on a VPN and a national gateway for a whole mobile carrier. It is
the first frame of a map and the thing a human then corrects — **never a
location to store on a record, and never rendered as "your address"**.
The payload carries `precision` and `ip_resolved` precisely so a UI can
tell which it is holding. What gets saved is what the person confirmed
through `geocoding/resolve`.

### Compatibility

Purely additive — a new endpoint, a new settings block whose defaults
change no existing behaviour, and one new key in `map/config`'s
`endpoints` dict. No migration, no removals, no changed responses. A
deployment that ignores all of it keeps the 0.4.0 surface unchanged; the
`geoip2` dependency is optional and is imported inside the call, so it
costs nothing to not install.

## [0.4.0] — 2026-08-24

### The defect: a location is chosen by a human, and this library shipped coordinates

A live product's listing composer offered **two raw fields, `latitude`
and `longitude`**. That is not a frontend oversight — it is the honest
consequence of a geo library whose default surface was a geocoder proxy
returning GeoJSON and nothing else. Choosing a place is a human act; a
library that hands over a `FeatureCollection` and leaves the address
line, the map, the position prompt and the confirmation step to each
product has not shipped the feature, it has shipped the parts.

0.4.0 is the server half of the picker. The React pair (`geo-react`,
which does not exist yet) builds against `docs/frontend-contract.md`.

### Fixed — `lang=ru` silently returned English addresses

`PhotonGeocoder.resolve_language` clamped any language outside
`PHOTON_LANGUAGES` to **`"en"`**. Photon does not degrade for an
unindexed language — it answers HTTP 400 — so the clamp is necessary;
clamping to English was the bug. The stock GraphHopper database carries
`default, en, de, fr` and nothing else, so a Russian deployment asking
for `lang=ru` received English street names, with **no error, no log
line and nothing wrong-looking in the response**. Wrong data that looks
right is worse than an outage.

The clamp now lands on `PHOTON_LANGUAGE_FALLBACK`, whose default
`"default"` is Photon's *local-name* mode: it returns the name as
written on the map — "Тверская улица" in Russia, "Hauptstraße" in
Germany. That is never worse than English and is exactly right for a
monolingual product. A regional tag is also retried on its base subtag
first (`ru-RU` → `ru`, `de-AT` → `de`), which an `Accept-Language`
header needs and the old code never did.

The clamp is no longer invisible either: **every response carries
`lang`**, the language actually asked of the upstream. Send `ru`, get
back `"lang": "default"`, and you can see what happened.

**Verdict on the deployment question: this was a call-site defect AND a
data-set fact, in that order.** The library was clamping to the wrong
value (fixed here, no redeploy needed). Making `ru` a *real* indexed
language is separate and larger: it requires building the Photon
database from the JSON dump with `java -jar photon.jar import -languages
ru,en …` instead of using the prebuilt one. Adding `"ru"` to
`PHOTON_LANGUAGES` **without** rebuilding the index turns every request
into a 502 — so `checks.W005`/`W006` now say all of this at deploy time,
with the exact command.

### Added — the picker's server half

- **`GET /geo/api/v1/geocoding/resolve`** and
  `geocoding.service.resolve_point()` — one coordinate pair in, one
  **confirmable place** out: the display line, the address components,
  the geohash to store, the runner-up candidates, and (opt-in via
  `?nearest=N`) the nearest known `Location` rows. This is the whole
  server side of "detect my position" and of a dropped map pin: one
  round trip, not three. An empty answer is an answer — the middle of a
  lake has coordinates too, and the picker shows "no address here", not
  a failure.
- **`properties.formatted` on every feature** — the one-line human label,
  assembled in the country's own postal order (`Тверская улица, 7` in
  Russia, `7 Tverskaya Street` in the US, per
  `ADDRESS_HOUSENUMBER_FIRST_COUNTRIES`), with a place name dropped when
  it merely repeats the city. Swappable fleet-wide via
  `ADDRESS_FORMATTER`. Every product was reassembling this by hand, each
  one differently, each one anglocentric.
- **`GET /geo/api/v1/map/config`** (public) and `basemap.build_map_config()`
  — tile template, **the attribution the ODbL licence obliges the map to
  display** (HTML and plain text, flagged `requires_attribution`), the
  zoom envelope, the operating bbox, the search-as-you-type discipline,
  the geohash precision, and the endpoint paths. It is unauthenticated
  because a map that cannot render until the visitor logs in is not a
  map. `checks.W007` refuses to let the OSM Foundation's public tile
  server reach production unnoticed.
- **Map-shaped narrowings on forward geocoding**, first-class on the
  facade rather than provider-specific spellings: `bbox` (hard — nothing
  outside the rectangle) and `bias_lat`/`bias_lon`/`bias_scale`/`zoom`
  (soft — near results rank higher). Until now `lat`/`lon` were stripped
  from a search request as "proxy-consumed", so a viewport-biased search
  was not expressible at all. An absent `bbox` inherits `MAP_BBOX`, so
  a country-scoped product is scoped without every caller remembering.
  A malformed explicit `bbox` is a **400**, not a silent widening.
- **`GEOCODER_PERMISSIONS`** — the proxy's guard is now a settings seam.
  The default is unchanged (authenticated only: geocoding burns a
  metered upstream), but a storefront that needs address search on a
  public page opens it from settings instead of subclassing four views,
  and **`GEOCODER_ANON_THROTTLE`** (default `10/min`) ships as the brake
  that then matters.
- **comm Functions `geo.geocode`, `geo.reverse_geocode`, `geo.map_config`**
  — the geocoding half of the surface was HTTP-only, so a module that
  wanted to stamp an address onto a coordinate had to import `stapel_geo`
  (this module's own first anti-pattern) or call itself over HTTP.
- **Flow `geo.pick_location`** — the human act, as a flow.
- `reverse` gained `radius_km`; Photon's upstream error **body** now
  survives into the `GeocoderError` message, so a misconfiguration is
  distinguishable from an outage in the logs.
- `docs/frontend-contract.md` — the contract `geo-react` builds against:
  endpoints, payloads, error shapes, the GeoJSON `[lon, lat]` trap, the
  language rule, and what the frontend still owns.

### Changed

- **`stapel-core` floor raised to `>=0.41.0`.** Core 0.41.0 hoisted
  `SerializerSeamMixin` / `StapelAPIView` into
  `stapel_core.django.api.views`; the geocoder views now inherit the
  canon and `stapel_geo.seams` is a re-export of it rather than a
  twenty-fifth local copy. The name stays exported — host code
  subclasses against it.
- `GeocodeProperties` gained `formatted`; `GeocodeResponse` gained
  `lang`. Both are additive, and `response_from_json` now ignores keys it
  does not know, so a 30-day `GeocodeCache` written by 0.3.x does not
  have to be flushed.
- `PHOTON_LANGUAGES`' documentation, everywhere it appears, now says what
  it actually is: a statement of fact about the Lucene index on disk, not
  a preference list.

### Compatibility

Additive for callers. Two behaviour changes to know about: a request for
an unindexed language returns local names instead of English (the fix),
and a **malformed** explicit `bbox` is now refused instead of ignored —
it never worked before, so nothing that worked stops working. Existing
`search`/`structured`/`reverse` payloads gain fields, lose none. No
migration.

## [0.3.6] — 2026-08-15

### Changed — `stapel-core` floor raised to 0.26.0

`docs/errors.json` carries an `owner` per entry, and only stapel-core 0.26.0
emits it. The floor lagged behind, so a consumer resolving an older core
regenerated an artifact without `owner` and the drift gate went red — the
field was declared but never required. The floor now matches the artifact
that is committed.

## [0.3.5] — 2026-08-02

### Fixed — `tests/test_contract.py` (added in 0.3.4) needs `stapel-tools` on the release track too

`ci.yml`'s test job only stayed green by accident: the `migration-lint`
step runs `pip install stapel-tools` before the test step, so
`stapel_tools.llms_txt` (imported by `tests/test_contract.py`) happened to
already be on the path. `publish.yml`'s test job has no migration-lint
step, so the same import failed there with `ModuleNotFoundError` — the
0.3.4 tag's publish run never got past `test` (no wheel was built,
nothing reached PyPI). Both workflows now install
`"stapel-tools>=0.9.1,<1"` explicitly in the "Install test dependencies"
step, matching the convention already used in `stapel-notifications`/
`stapel-profiles`/`stapel-shop`.

## [0.3.4] — 2026-08-02

Packaging/CI only, no runtime change.

### Changed
- CI now tests Python 3.14 (the version production runs) alongside 3.11-3.13.
- Badge canon; migration-lint step uncommented now that `stapel-tools` is on PyPI.
- Contract documents (`docs/capabilities.json`, `docs/flows.json`,
  `docs/errors.json`, `CONFIG.MD`) ship inside the wheel via `package-data` (#184).
- `docs/llms.txt` — the fifth contract artifact (badge-canon §3), rendered
  from the hand-authored `docs/capabilities.json` plus the codegen'd
  triad, wired into `make contract`/`contract-check`, and now packaged
  into the wheel alongside the other contract artifacts.

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
