# stapel-geo — MODULE.md

> Agent-facing map of this module: what it provides, where to extend it
> without forking, and what not to do. Kept in the same PR as any change
> to a seam. See also README.md and CHANGELOG.md.

## What this module provides

- **Location tree** (`models.Location`, `django-treenode`): hierarchical
  reference places (country -> region -> city) as **flat points** —
  `lat`/`lon` floats, an indexed `geohash` auto-encoded in `save()`, and a
  stable cross-service **UUID**. No geometry columns, no GDAL, no spatial
  DB — the PostGIS/GADM polygon layer was removed in 0.3.0.
- **Proximity search facade** (`stapel_geo.search`): three verbs —
  `nearby` (top-K nearest), `radius` (membership within N km), `bbox`
  (rectangle, `min_lon > max_lon` = antimeridian wrap) — behind one
  swappable backend key. The default backend runs geohash prefix
  expansion over the primary DB (the proven 9-cell neighbour machinery:
  equator/antimeridian/pole safe, exact-haversine ranked); Redis
  `GEOSEARCH` ships as the first scale backend; ES/Solr are named stubs.
- **Geocoder proxy** (`geocoding/`): forward / structured / reverse
  geocoding behind a provider **merge-registry**, JWT-guarded, throttled
  (scope `"geocoding"`), cached and spend-ledgered per call, returning a
  normalized GeoJSON `GeocodeResponse`.
- **comm surface**: Functions `geo.nearby` / `geo.radius` / `geo.bbox` /
  `geo.geohash_encode` / `geo.resolve` (consumers query geo by name,
  never importing it; `geo.geohash_encode` is how listings stamp their
  own `geohash` column).
- **HTTP canon**: the host mounts `path("geo/", include("stapel_geo.urls"))`
  → `/geo/api/v1/locations/...` + `/geo/api/v1/geocoding/...`
  (api-versioning.md: the version segment is part of the contract; v1
  patterns live in `urls_v1.py`, a future v2 mounts alongside).
- **Contract triad**: committed `docs/{schema,flows,errors}.json`
  (regenerate with `make contract`; Python 3.12 pin).

## Extension points (fork-free)

### Settings — `STAPEL_GEO` namespace (`conf.py`)

Resolution per key: `settings.STAPEL_GEO[key]` → flat Django setting → env
var → default. Read lazily at call time. Full key table: README.md.

| Seam | Key | Semantics |
|---|---|---|
| Search backend | `SEARCH_BACKEND` (dotted path) | **REPLACE** (single strategy) |
| Geocoder default | `GEOCODER` (a **name**) | picks from the registry |
| Geocoder registry | `GEOCODERS` (`{name: dotted_path}`) | **MERGE** over `BUILTIN_GEOCODERS`; `None`/`""` removes |
| Geocode cache | `GEOCODE_CACHE_POLICY` (dotted path) | **REPLACE** |

### Search backend seam — `SEARCH_BACKEND` (`search/base.py`)

Implement the `GeoSearchBackend` protocol (three verbs) and point the key
at your class:

```python
from stapel_geo.search.base import GeoSearchBackend  # typing only

class MyBackend:
    def nearby(self, lat, lon, *, limit, precision=None): ...
    def radius(self, lat, lon, radius_km, *, limit=None): ...
    def bbox(self, min_lat, min_lon, max_lat, max_lon, *, limit=None): ...

STAPEL_GEO = {"SEARCH_BACKEND": "myproject.geo.MyBackend"}
```

Contract: hits are `(key, distance_km)` pairs (bare keys for `bbox`)
where **key = `str(Location.uuid)`** — the service layer joins keys back
to rows, so a side-index backend (Redis, ES) only stores ids + points.
`checks.W003/W004` warn on a broken value. Shipped backends:
`search/postgres.py` (default), `search/redis.py` (side index;
`rebuild()` re-indexes; receivers connected in `apps.py` sync it),
`search/elasticsearch.py` + `search/solr.py` (stubs with pointers).

### Geocoder provider seam — the registry (`geocoding/providers.py`)

`BUILTIN_GEOCODERS = {photon, nominatim, google, yandex}`. Add or replace
providers without forking:

```python
from stapel_geo.geocoding.base import Geocoder

class MyGeocoder(Geocoder):
    name = "mine"
    def search(self, query, *, lang=None, limit=None, **params): ...
    def reverse(self, lat, lng, *, lang=None, limit=None, **params): ...
    def structured(self, *, lang=None, limit=None, **params): ...

STAPEL_GEO = {"GEOCODERS": {"mine": "myproject.geo.MyGeocoder"},
              "GEOCODER": "mine"}
# or at runtime: stapel_geo.register_geocoder("mine", "myproject.geo.MyGeocoder")
```

Contract: each verb returns a normalized `GeocodeResponse` (GeoJSON
FeatureCollection) and raises `GeocoderError` when the upstream is
unreachable (surfaced as HTTP 502 `error.502.geocoder_unavailable`).
Read config lazily via `geo_settings`. `google`/`yandex` are **key-gated
stubs** — hosts implement them with their own PAYG keys (stapel never
bundles metered keys). The public-Nominatim provider self-enforces 1 rps;
it is a dev/fallback, not a production default.

### Geocode cache seam — `GEOCODE_CACHE_POLICY` (`geocoding/cache.py`)

`GeocodeCachePolicy` ABC (`should_cache` / `lookup` / `store`). The
default `LedgerCachePolicy` answers from the `GeocodeCache` ledger table
within `GEOCODE_CACHE_TTL_DAYS`. The **ledger row is written on every
call regardless** (ok / error / cache_hit + duration_ms) — caching is a
read seam, accounting is not optional (the PromptLog pattern).

### Throttle

`geocoding/views.py:GeocodingThrottle` — a `ScopedRateThrottle`
(scope `"geocoding"`) whose rate comes from
`STAPEL_GEO["GEOCODER_THROTTLE"]`. Subclass + swap `throttle_classes` in
a view subclass for per-verb rates.

### Serializer seams (`views.py`, `geocoding/views.py`)

`seams.SerializerSeamMixin` — subclass a geocoder view, set
`response_serializer_class`, remount the URL. `LocationViewSet` is a DRF
`ModelViewSet`: swap `serializer_class` / `get_serializer_class` in a
subclass and remount.

## Anti-patterns (do NOT)

- **Do not `import stapel_geo` from another module** — consume the comm
  Functions by name (`geo.nearby`, `geo.geohash_encode`, ...). Listings'
  `geohash` column is stamped via `geo.geohash_encode`, not via a Python
  import.
- **Do not bring back polygons/GDAL** — boundary geometry, GADM imports
  and `ST_Contains` queries are out of scope since 0.3.0 (owner
  directive). If a real demand appears, that is a separate opt-in add-on
  package, not a change to this module.
- **Do not bundle provider API keys** — google/yandex stay stubs here;
  keys are host configuration.
- **Do not bypass the facade** — new search verbs go through
  `stapel_geo.search.get_backend()` (one code path per verb), never
  straight to the ORM from views/functions.
- **Do not add unversioned HTTP paths** — the canon is `/geo/api/v1/...`;
  a breaking change mounts `v2` alongside, it never edits v1 in place.

## Testing

`pytest tests/` — self-contained (`conftest.py` configures in-memory
SQLite; no GDAL, no external services; the Redis backend is tested
against an in-memory fake, and a live-Redis failure path asserts saves
never break). comm schemas are enforced (`VALIDATE_SCHEMAS=True`).
`make contract-check` guards the committed contract triad;
`make migration-lint` gates migrations.
