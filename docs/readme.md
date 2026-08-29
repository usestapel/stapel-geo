## What this is

- **Location tree** — hierarchical reference places (`django-treenode`):
  flat lat/lon points with an auto-encoded, indexed geohash and a stable
  cross-service UUID. No polygons.
- **Proximity search facade** — `nearby` (top-K) / `radius` (membership) /
  `bbox` (viewport, antimeridian-aware) behind one swappable backend key.
  The default runs on your primary database via geohash prefix expansion
  (correct across the equator, the antimeridian and the poles, ranked by
  exact haversine); a Redis `GEOSEARCH` side-index backend ships for the
  hot set; Elasticsearch/Solr are named stubs.
- **Geocoder proxy** — forward / structured / reverse / resolve behind a
  provider merge-registry (`photon` self-hosted default, `nominatim`
  keyless dev/fallback, `google`/`yandex` key-gated stubs), throttled,
  cached (30-day TTL) and spend-ledgered per call. Forward search takes
  the map's own narrowings: a hard `bbox` and a soft viewport bias.
- **The location picker's server half** — because a place is chosen by a
  *human*, not typed as two decimals:
  - every feature carries `properties.formatted`, the display line, in
    the country's own postal order;
  - `geocoding/resolve?lat=&lon=` turns one coordinate pair into a
    **confirmable place** (label, components, geohash, alternatives) in
    one round trip — the whole server side of "detect my position" and
    of a dropped map pin;
  - `map/config` (public) hands the frontend its tile template, **the
    attribution the ODbL licence obliges the map to display**, the zoom
    envelope, the operating bbox and the debounce discipline.

  The React pair builds against `docs/frontend-contract.md`.
- **Where to open the map before anyone is asked** — `ip` (public) places
  the visitor from the address their request arrived on, so a picker
  opens on a city while the browser's geolocation prompt is still
  unanswered, or after it was refused. Offline `maxmind` database or a
  single configured `static` point, behind the same kind of provider
  registry as the geocoder, with the map's own default centre as the
  floor under both. Coarse on purpose: city-at-best, wrong on a VPN or a
  carrier NAT, and `source`/`precision`/`ip_resolved` come back with the
  point so a UI never presents a guess as the user's address.
- **comm surface** — `geo.nearby` / `geo.radius` / `geo.bbox` /
  `geo.geohash_encode` / `geo.resolve` / `geo.geocode` /
  `geo.reverse_geocode` / `geo.map_config`: consumers (listings,
  calendar) query geo by name, never importing it.

## Quick start

```bash
pip install "stapel-geo[redis]"  # + the Redis search backend
pip install "stapel-geo[ipgeo]"  # + the offline MaxMind reader for `ip`
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
| `geocoding/search?q=` | Forward geocoding, `?bbox=` + `?bias_lat=&bias_lon=` (guarded + throttled) |
| `geocoding/structured?city=&street=` | Structured address search |
| `geocoding/reverse?lat=&lon=` | Reverse geocoding (raw candidates) |
| `geocoding/resolve?lat=&lon=` | **One coordinate pair → one confirmable place** |
| `map/config` | Basemap + picker configuration (**public**) |
| `ip` | Where the caller appears to be, for the map's opening centre (**public**, throttled) |

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
| `PHOTON_URL` | `http://localhost:2322` | Photon instance the default provider proxies. |
| `PHOTON_LANGUAGES` | `[default,en,de,fr]` | What the Photon index **actually carries** — not a preference list. Photon 400s on anything else. |
| `PHOTON_LANGUAGE_FALLBACK` | `"default"` | Where an unindexed language clamps. `default` = Photon's local-name mode (Russian in Russia). |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Nominatim base (public: 1 rps, dev/fallback). |
| `GEOCODER_TIMEOUT` | `10` | Geocoder HTTP timeout (s). |
| `GEOCODER_THROTTLE` / `GEOCODER_ANON_THROTTLE` | `30/min` / `10/min` | Scoped throttle rates (identified / anonymous). |
| `GEOCODER_PERMISSIONS` | `[IsNotAnonymousUser]` | Guard of the proxy verbs. Set to `AllowAny` for a public address search. |
| `GEOCODE_CACHE_POLICY` | `…geocoding.cache.LedgerCachePolicy` | Cache seam (dotted path). |
| `GEOCODE_CACHE_TTL_DAYS` | `30` | Default cache TTL. |
| `ADDRESS_FORMATTER` | `…geocoding.format.format_address` | Builds `properties.formatted` (seam). |
| `MAP_TILE_URL` / `MAP_TILE_ATTRIBUTION_*` | OSM public tiles / OSM credit | Basemap and its **mandatory** attribution. The default tile server is a dev default (`W007`). |
| `MAP_BBOX` | `None` | The product's operating area; also the default hard restriction on forward geocoding. |
| `MAP_*` (zoom, centre, debounce) | see `CONFIG.MD` | The rest of the picker's configuration. |
| `IP_LOCATOR` | `"maxmind"` | Default IP locator **name** (registry key). |
| `IP_LOCATORS` | `{}` | Extra locators, merged over the built-ins (`None` removes). |
| `IP_MAXMIND_DB` | `""` | Path to your own offline GeoLite2/GeoIP2 City `.mmdb`. Nothing is bundled — MaxMind forbids redistributing it. |
| `IP_STATIC_POINT` / `IP_STATIC_LABEL` / `IP_STATIC_PRECISION` | `None` / `""` / `"city"` | The `static` locator's one answer for everybody — a single-city product's honest one. |
| `IP_FALLBACK_CENTER` / `IP_FALLBACK_LABEL` | `None` / `""` | Where to open when the locator has nothing. Unset, `MAP_DEFAULT_CENTER` answers. |
| `IP_TRUSTED_PROXY_DEPTH` | `0` | How many proxies you own. `0` = `REMOTE_ADDR` only; **`1` behind one nginx**. Counted from the right of `X-Forwarded-For`, so a forged prefix is inert (`W010`). |
| `IP_CLIENT_IP_RESOLVER` | `…ipgeo.client_ip.client_ip_from_request` | The whole client-address decision as one function (seam). |
| `IP_PERMISSIONS` | `[AllowAny]` | Guard of the `ip` endpoint — open by design: the caller has no account yet. |
| `IP_THROTTLE` / `IP_ANON_THROTTLE` | `120/min` / `60/min` | Scoped throttle rates (scope `geo_ip`); the anonymous one is the live one here. |
| `IP_CACHE_TTL_S` | `3600` | How long one address's answer is cached (`0` disables). |

> **Sending `lang`?** Send `default`, or nothing. `PHOTON_LANGUAGES` is
> what the index on disk carries, and Photon refuses anything else with
> HTTP 400 rather than degrading. Requests for an unindexed language
> clamp to `PHOTON_LANGUAGE_FALLBACK` (`"default"` = the local name on
> the map, which for a single-country product is already the right
> language), and the response's `lang` field tells you what was really
> used. To index another language for real, build the Photon database
> from the JSON dump with `photon.jar import -languages …`; listing it
> here **without** rebuilding turns every request into a 502.
> `manage.py check` says all of this (`stapel_geo.W005`/`W006`).

> **Behind a proxy?** Set `IP_TRUSTED_PROXY_DEPTH` to the number of hops
> you actually own (`1` behind a single nginx). Leave it at `0` there and
> every visitor geolocates to your proxy; raise it past what you own and
> a caller picks their own IP by typing an `X-Forwarded-For` header. The
> chain `X-Forwarded-For ++ [REMOTE_ADDR]` is counted from the **right**,
> which is what keeps a forged prefix inert. `manage.py check` says this
> too (`stapel_geo.W008`/`W009`/`W010`).

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

## Extension points

Swappable from settings, no fork: the search backend (`SEARCH_BACKEND`),
the geocoder registry (`GEOCODERS` / `GEOCODER`), the geocode cache
(`GEOCODE_CACHE_POLICY`), the display line (`ADDRESS_FORMATTER`), the IP
locator registry (`IP_LOCATORS` / `IP_LOCATOR` — same merge semantics as
the geocoders'), and which address a request came from
(`IP_CLIENT_IP_RESOLVER`, the proxy-trust decision as one function).

See [MODULE.md](https://github.com/usestapel/stapel-geo/blob/main/MODULE.md) — the agent-facing map of every fork-free seam, and
[CHANGELOG.md](https://github.com/usestapel/stapel-geo/blob/main/CHANGELOG.md) — including what 0.3.0 removed and why.
