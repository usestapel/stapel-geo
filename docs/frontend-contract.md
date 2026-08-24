# stapel-geo — the contract `geo-react` builds against

> Written for the agent creating the `geo-react` package in the
> stapel-react monorepo. This is the server side of the location picker:
> the endpoints, the payloads, the error shapes, and the four decisions
> the backend has already made so the frontend does not remake them.
> Backend version: **stapel-geo 0.4.0**.

## 0. Why this document exists

A live product's listing composer shipped **two raw fields, `latitude`
and `longitude`**. That is not a frontend bug. It is what happens when a
geo library ships coordinates and calls it a feature: a location is
chosen by a *human*, so the library owes the human half — an address to
read, a map to point at, a position to detect — in its **defaults**, not
as a recipe each product follows differently.

0.4.0 is the backend half. `geo-react` is the other half. Between them
the default skin must be able to do all of this with no product-specific
code:

1. show a map;
2. search for an address as the user types;
3. offer "use my current position";
4. let the user drop / drag a pin;
5. show back the address that was chosen, for confirmation;
6. hand the product `{lat, lon, geohash, address components}`.

## 1. Mount point and versioning

The host mounts `path("geo/", include("stapel_geo.urls"))`, giving:

```
/geo/api/v1/…
```

The version segment is part of the contract; v1 is never edited in place.
`geo-react` should take the mount prefix as configuration (default
`/geo/`) and append the paths that `GET /geo/api/v1/map/config` returns in
its `endpoints` object — **read them from there rather than hardcoding
four strings.**

**No trailing slash** on the geocoding verbs: `…/geocoding/search` is the
endpoint, `…/geocoding/search/` is a 404. (`locations/` beside them *is* a
router route and accepts either.)

## 2. The five calls

### 2.1 `GET /geo/api/v1/map/config` — public, call it first

No authentication. This is the only call that works before login, and it
is what lets the map render for an anonymous visitor.

```jsonc
{
  "tiles": {
    "url_template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "subdomains": [],
    "attribution_html": "&copy; <a href=\"…\">OpenStreetMap</a> contributors",
    "attribution_text": "© OpenStreetMap contributors",
    "policy_url": "https://operations.osmfoundation.org/policies/tiles/",
    "requires_attribution": true,
    "min_zoom": 2,
    "max_zoom": 19
  },
  "default_center": null,          // [lat, lon] or null = "no opinion"
  "default_zoom": 13,
  "picked_zoom": 17,               // where the map settles after a pick
  "bbox": null,                    // [min_lon, min_lat, max_lon, max_lat] or null
  "geolocation": true,             // offer the browser position prompt?
  "search_min_chars": 3,
  "search_debounce_ms": 350,
  "geohash_precision": 8,
  "endpoints": {
    "search": "api/v1/geocoding/search",
    "structured": "api/v1/geocoding/structured",
    "reverse": "api/v1/geocoding/reverse",
    "resolve": "api/v1/geocoding/resolve",
    "locations_nearby": "api/v1/locations/nearby-by-coords"
  }
}
```

**`attribution_html` / `attribution_text` are not optional.** OpenStreetMap
data is ODbL-licensed and the tile policy requires visible credit; a map
that renders without the line is a licence violation, not a style choice.
`requires_attribution` says so in-band so the component can refuse to
render a map with the credit suppressed.

`bbox` and `search_min_chars` / `search_debounce_ms` are the product's
operating discipline: respect them, they exist so one keystroke is not one
upstream request and so a Russian marketplace does not offer a street in
Ohio.

### 2.2 `GET …/geocoding/search` — search-as-you-type

| param | type | notes |
|---|---|---|
| `q` | string | **required** — the raw text the user typed |
| `lang` | string | see §4 — **do not send `ru`**, see the language section |
| `limit` | int | clamped to 50 |
| `bbox` | `min_lon,min_lat,max_lon,max_lat` | hard restriction; **omit it** and the server applies the product's own `MAP_BBOX` |
| `bias_lat`, `bias_lon` | float | soft bias: the map's current centre |
| `bias_scale` | float 0.0–1.0 | how strong the bias is |
| `zoom` | int | the map's current zoom, for bias scaling |

Response: a GeoJSON `FeatureCollection` (§3).

The bias pair is what makes the field feel local: pass the map centre on
every keystroke and "Ленина" resolves to the street the user is looking
at, not to one 4000 km away.

### 2.3 `GET …/geocoding/structured` — components, not free text

`city`, `street`, `housenumber`, `postcode`, `countrycode`, plus `lang` /
`limit`. Same response shape. Useful when the product already has a split
address form. Note: the **prebuilt** Photon databases the fleet runs do
not support structured search — it needs a self-built index. Treat this
verb as optional in the default skin.

### 2.4 `GET …/geocoding/reverse` — coordinates → place(s), raw

`lat`, `lon` (both required), `lang`, `limit`, `radius_km`. Returns the
same `FeatureCollection`. Use it when you want the raw candidates. For the
picker, prefer `resolve`.

### 2.5 `GET …/geocoding/resolve` — **the one the picker uses**

This is the "detect my position" round trip and the "pin was dropped"
round trip. One call, everything a confirmation step renders.

| param | type | notes |
|---|---|---|
| `lat`, `lon` | float | **required** |
| `lang` | string | §4 |
| `limit` | int | how many candidates to consider (1 pick + alternatives) |
| `nearest` | int | also return N known `Location` rows; **default 0 = the tree is not queried at all** |
| `radius_km` | float | how far the provider may look |

```jsonc
{
  "lat": 55.7575,
  "lon": 37.6114,
  "geohash": "ucftpvbx",          // what you store alongside lat/lon
  "lang": "default",              // the language ACTUALLY used — see §4
  "formatted": "Центральный телеграф, Тверская улица, 7, Москва, Россия",
  "address": { /* GeocodeProperties, §3 */ },
  "feature": { /* the best candidate as a GeoJSON Feature */ },
  "alternatives": [ /* further Features, best-first: "not this one?" */ ],
  "nearest": [ { "uuid": "…", "name": "Москва", "country": "Россия",
                 "display_name": "…", "distance_km": 1.42 } ]
}
```

Notes that matter for the UI:

- **`feature.geometry.coordinates` may differ from `lat`/`lon`.** The
  geocoder snaps to the matched object. Decide deliberately which one you
  store — the user's pin or the geocoder's snap — and show the same one
  on the map.
- **An empty answer is not an error.** The middle of a lake has
  coordinates too: `formatted: null`, `feature: null`, `alternatives: []`,
  and `geohash` still present. Render "no address here", not a failure.
- `nearest` is empty unless you ask, and is only meaningful when the host
  populates the `Location` reference tree. Do not build the default skin
  around it.

### Browser geolocation, end to end

```js
navigator.geolocation.getCurrentPosition(async ({ coords }) => {
  const r = await fetch(
    `${prefix}${endpoints.resolve}?lat=${coords.latitude}&lon=${coords.longitude}`
  );
  // r.ok -> render r.json().formatted for confirmation
});
```

The permission prompt is yours; everything after it is one call. Handle
the browser's own `PositionError` (denied / unavailable / timeout) in the
component — the server never sees it.

## 3. The feature shape

Every verb that returns places returns:

```jsonc
{
  "type": "FeatureCollection",
  "lang": "default",              // the language actually used upstream
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [37.6114, 55.7575] },  // [lon, lat]!
      "properties": {
        "formatted": "Центральный телеграф, Тверская улица, 7, Москва, Россия",
        "name": "Центральный телеграф",
        "country": "Россия", "countrycode": "RU",
        "state": "Москва", "county": null, "city": "Москва",
        "district": "Тверской", "street": "Тверская улица",
        "housenumber": "7", "postcode": "125009",
        "osm_key": "amenity", "osm_value": "post_office",
        "osm_type": "W", "osm_id": 123456,
        "extent": [37.60, 55.75, 37.62, 55.76]   // [minLon, minLat, maxLon, maxLat] or null
      }
    }
  ]
}
```

Two things to hold on to:

- **`coordinates` is `[lon, lat]`** — GeoJSON order, the opposite of every
  `lat, lon` parameter in this API. This is the single most common bug in
  map code. Convert once, at the boundary.
- **`properties.formatted` is the display line, and it ships.** Do not
  reassemble `name`/`street`/`housenumber`/`city`/`country` in the
  component — the server already did it in the right order for the
  country (`Тверская улица, 7` in Russia, `7 Tverskaya Street` in the US),
  and a host can override the whole rule fleet-wide with one setting.
  Any field can be `null`; `formatted` can be `""` for a featureless
  place.
- `extent` is the feature's own bounding box when the provider knows one —
  use it to fit the map to a city instead of guessing a zoom.

## 4. Language — read this before sending `lang`

**Send `lang=default`, or send nothing.** Do not send `lang=ru`.

Photon indexes only the languages its database was *built* with. The
prebuilt GraphHopper dumps the fleet runs carry `default, en, de, fr` and
nothing else, and Photon **refuses** an unindexed language with HTTP 400
rather than degrading. `default` is Photon's *local-name* mode: it returns
the name as written on the map, which in Russia is Russian.

The server clamps for you (`PHOTON_LANGUAGES` / `PHOTON_LANGUAGE_FALLBACK`),
so `lang=ru` no longer silently becomes English the way it did before
0.4.0. But the clamp is still a clamp, and **the response tells you what
actually happened**: the `lang` field on every response is the language
the upstream was really asked for. If you send `ru` and get back
`"lang": "default"`, that is the clamp, working as designed.

Practical rule for the component: omit `lang` entirely and let
`Accept-Language` do its job, or send `default`. Expose a `lang` prop for
deployments whose index really does carry their language.

## 5. Auth, throttling, and the anonymous case

- `map/config` — **public**, always.
- The four geocoding verbs — guarded by
  `STAPEL_GEO["GEOCODER_PERMISSIONS"]`, which **defaults to authenticated
  only**. An anonymous caller gets **401/403**, and that is a
  configuration fact of the deployment, not a bug to work around.
- A product that wants address search on a public page sets
  `GEOCODER_PERMISSIONS = ["rest_framework.permissions.AllowAny"]`; the
  anonymous rate limit (`GEOCODER_ANON_THROTTLE`, default `10/min`) then
  applies.
- Throttled callers get **429**. With `search_debounce_ms` respected this
  should not happen in normal typing; handle it anyway — show the last
  good suggestions and stop firing, do not surface a red error for a rate
  limit.

Design consequence: the component must accept "geocoding is not available
to me" as a first-class state, distinct from "the geocoder is down". If
`map/config` succeeds but `search` 401s, the map still renders and the
pin still drops — the product just cannot resolve an address until the
user signs in.

## 6. Error envelope

Every error is the Stapel envelope, HTTP status plus:

```jsonc
{ "localizable_error": "error.400.lat_lon_required",
  "error": "Valid latitude and longitude are required",
  "params": {} }
```

Branch on `localizable_error`; `error` is a translated string for display.

| status | `localizable_error` | when |
|---|---|---|
| 400 | `error.400.lat_lon_required` | `lat`/`lon` missing, non-numeric, NaN/inf, or out of range |
| 400 | `error.400.invalid_bbox` | `bbox` is not four numbers in range (a wrapping `min_lon > max_lon` is legal) |
| 400 | `error.400.invalid_params` | a malformed `bias_*` / `zoom` / `nearest` / `radius_km` |
| 401 / 403 | — | anonymous caller under the default permission |
| 429 | — | throttled (`GEOCODER_THROTTLE` / `GEOCODER_ANON_THROTTLE`) |
| 502 | `error.502.geocoder_unavailable` | the upstream geocoder is unreachable or answered garbage |

**502 is retryable; 400 is not.** And note the asymmetry that matters for
UX: a *successful* call with zero features means "nothing matched" — an
empty state, not an error.

## 7. What `geo-react` still owns

The backend deliberately does **not** decide these:

- Which map library draws the tiles (Leaflet, MapLibre, …) and its
  bundle/CSP cost. The server hands over a tile template and an
  attribution obligation, nothing more.
- The geolocation permission prompt and its denial states.
- Debounce/abort mechanics of the search field (the server ships the
  *numbers*; the component implements the behaviour, including cancelling
  in-flight requests when the query changes).
- Which point gets stored when the geocoder's snap disagrees with the
  user's pin.
- Marker/pin visuals, keyboard accessibility, and the confirmation copy.

## 8. Reference

- Settings table: `CONFIG.MD` (all `MAP_*`, `ADDRESS_*`, `PHOTON_*`,
  `GEOCODER_*` keys).
- Extension seams: `MODULE.md`.
- Machine contract: `docs/schema.json`, `docs/flows.json`,
  `docs/errors.json` — the flow `geo.pick_location` is this document's
  flow, `geo.geocode_address` is the proxy underneath it.
