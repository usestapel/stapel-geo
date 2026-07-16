# stapel-geo

[![CI](https://github.com/usestapel/stapel-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/usestapel/stapel-geo/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usestapel/stapel-geo/graph/badge.svg)](https://codecov.io/gh/usestapel/stapel-geo)
[![PyPI](https://img.shields.io/pypi/v/stapel-geo.svg)](https://pypi.org/project/stapel-geo/)

Geohash proximity search and geocoding for the [Stapel framework](https://github.com/usestapel)
— composable Django apps that deploy as a monolith or as microservices
without changing module code. **No GDAL, no PostGIS, no spatial database.**

- **Location tree** — hierarchical reference places (`django-treenode`):
  flat lat/lon points with an auto-encoded, indexed geohash and a stable
  cross-service UUID. No polygons.
- **Proximity search facade** — `nearby` (top-K) / `radius` (membership) /
  `bbox` (viewport, antimeridian-aware) behind one swappable backend key.
  The default runs on your primary database via geohash prefix expansion
  (correct across the equator, the antimeridian and the poles, ranked by
  exact haversine); a Redis `GEOSEARCH` side-index backend ships for the
  hot set; Elasticsearch/Solr are named stubs.
- **Geocoder proxy** — forward / structured / reverse geocoding behind a
  provider merge-registry (`photon` self-hosted default, `nominatim`
  keyless dev/fallback, `google`/`yandex` key-gated stubs), throttled,
  cached (30-day TTL) and spend-ledgered per call.
- **comm surface** — `geo.nearby` / `geo.radius` / `geo.bbox` /
  `geo.geohash_encode` / `geo.resolve`: consumers (listings, calendar)
  query geo by name, never importing it.

## Install

```bash
pip install stapel-geo           # default backend needs nothing extra
pip install "stapel-geo[redis]"  # + the Redis search backend
```

```python
INSTALLED_APPS = [
    # ...
    "stapel_geo",
]

# urls.py — the canonical versioned surface /geo/api/v1/...
path("geo/", include("stapel_geo.urls"))
# ... or mount only the geocoder proxy:
path("geo/api/v1/geocoding/", include("stapel_geo.geocoding.urls"))
```

Plain `manage.py migrate` — any Django database backend works.

## HTTP surface (`/geo/api/v1/`)

| Route | What |
|---|---|
| `locations/` | List roots / search by name (`?search=`) |
| `locations/{id-or-uuid}/` | Location detail (lat/lon/geohash, tree parent) |
| `locations/countries/` | Root level of the tree |
| `locations/by-parent/{id}/` | Children of a node |
| `locations/nearby-by-coords/?lat=&lon=` | Top-K nearest (exact `distance_km`) |
| `locations/nearby-by-geohash/?geohash=` | Same, geohash input |
| `locations/validate-uuid/{uuid}/` | Cross-service reference check |
| `geocoding/search?q=` | Forward geocoding (JWT + throttle) |
| `geocoding/structured?city=&street=` | Structured address search |
| `geocoding/reverse?lat=&lon=` | Reverse geocoding |

## Settings (`STAPEL_GEO`)

| Key | Default | Meaning |
|---|---|---|
| `SEARCH_BACKEND` | `…search.postgres.PostgresGeoSearchBackend` | Search engine behind nearby/radius/bbox (dotted path). |
| `REDIS_URL` / `REDIS_GEO_KEY` | `redis://localhost:6379/0` / `stapel:geo:locations` | Redis backend connection + side-index key. |
| `GEOHASH_PRECISION` | `8` | Stored geohash precision (1-12 chars). |
| `NEARBY_PRECISION` | `6` | Default precision for coordinate nearby search. |
| `NEARBY_LIMIT` / `NEARBY_MAX_LIMIT` | `10` / `50` | Default / max search results. |
| `GEOCODER` | `"photon"` | Default geocoder **name** (registry key). |
| `GEOCODERS` | `{}` | Extra providers, merged over the built-ins (`None` removes). |
| `PHOTON_URL` / `PHOTON_LANGUAGES` | `http://localhost:2322` / `[default,en,de,fr]` | Photon provider knobs. |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Nominatim base (public: 1 rps, dev/fallback). |
| `GEOCODER_TIMEOUT` | `10` | Geocoder HTTP timeout (s). |
| `GEOCODER_THROTTLE` | `30/min` | DRF scoped throttle rate for the proxy. |
| `GEOCODE_CACHE_POLICY` | `…geocoding.cache.LedgerCachePolicy` | Cache seam (dotted path). |
| `GEOCODE_CACHE_TTL_DAYS` | `30` | Default cache TTL. |

## comm Functions

```python
from stapel_core.comm import call

call("geo.nearby", {"lat": 49.61, "lon": 6.13, "limit": 5})
call("geo.radius", {"lat": 49.61, "lon": 6.13, "radius_km": 25})
call("geo.bbox", {"min_lat": 49, "min_lon": 5, "max_lat": 50, "max_lon": 7})
call("geo.geohash_encode", {"lat": 49.61, "lon": 6.13})   # -> {"geohash": ...}
call("geo.resolve", {"uuid": "<location-uuid>"})
```

`min_lon > max_lon` in `geo.bbox` means the box crosses the antimeridian.

## Swapping the search backend

```python
STAPEL_GEO = {"SEARCH_BACKEND": "stapel_geo.search.redis.RedisGeoSearchBackend"}
```

The Redis backend is a **side index**: the primary DB stays the source of
truth; `post_save`/`post_delete` keep it in sync and
`RedisGeoSearchBackend().rebuild()` re-indexes from scratch. Implement
`stapel_geo.search.base.GeoSearchBackend` (three verbs) to bring your own
engine — see `MODULE.md`.

## Docs

- [MODULE.md](MODULE.md) — extension points (agent-facing map).
- [CHANGELOG.md](CHANGELOG.md) — including what 0.3.0 removed and why.
- `docs/{schema,flows,errors}.json` — the committed contract triad
  (regenerate with `make contract`).
- Error reference: [English](docs/errors.en.md) · [Русский](docs/errors.ru.md).

## License

MIT
