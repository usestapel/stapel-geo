# Flows

### [Geocode an address](geo.geocode_address.md)

`geo.geocode_address` · 7 steps · Actors: Authenticated user

A logged-in user turns free text, address components or a coordinate into normalized GeoJSON places through the swappable provider registry (photon by default; nominatim as keyless dev/fallback). Every call is throttled (scope 'geocoding'), cached (GeocodeCache, 30-day TTL) and written to the spend ledger.

### [Browse the location tree](geo.location_browse.md)

`geo.location_browse` · 4 steps · Actors: Any authenticated or anonymous user

A user drills into the hierarchical location reference (country -> region -> city) or searches it by name — picking a location for a listing, a profile, or a filter. Flat reference data: no geometry, each node is a point with a geohash.

### [Find locations near a point](geo.location_nearby.md)

`geo.location_nearby` · 5 steps · Actors: Any user, Consumer modules via comm

A consumer (listings' radius filter, a 'near me' UI) asks which known locations are nearest to a coordinate or geohash. Served by the swappable search backend (STAPEL_GEO['SEARCH_BACKEND']) — geohash prefix expansion over the primary DB by default, correct across the equator, the antimeridian and the poles.

### [Validate and expand a location reference](geo.location_resolve.md)

`geo.location_resolve` · 2 steps · Actors: Consumer modules via comm, Frontends

A module holding an opaque location UUID (a listing's location_id, a calendar address) checks it still exists and expands it to a display summary. A missing UUID is a normal answer, not an error.

### [Pick a location on a map](geo.pick_location.md)

`geo.pick_location` · 7 steps · Actors: Any user, Frontends (geo-react)

A human chooses WHERE something is — a listing's address, a meeting point, a service area — by searching for it, by letting the browser report their position, or by dragging a pin. The library owns the whole round trip: the basemap's tile layer and its attribution obligations, the search-as-you-type discipline, and the single call that turns a coordinate into an address the user can confirm. A product that only offers raw latitude and longitude fields has not integrated this flow.

## Endpoint → flow

- `GET /geo/api/v1/^locations/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/by-parent/(?P<parent_id>\d+)/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/by-parent/(?P<parent_id>\d+)/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/countries/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/countries/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_browse
- `GET /geo/api/v1/^locations/nearby-by-coords/?$` → geo.location_nearby
- `GET /geo/api/v1/^locations/nearby-by-coords/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_nearby
- `GET /geo/api/v1/^locations/nearby-by-geohash/?$` → geo.location_nearby
- `GET /geo/api/v1/^locations/nearby-by-geohash/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_nearby
- `GET /geo/api/v1/^locations/validate-uuid/(?P<uuid>[^/.]+)/?$` → geo.location_resolve
- `GET /geo/api/v1/^locations/validate-uuid/(?P<uuid>[^/.]+)/?\.(?P<format>[a-z0-9]+)/?$` → geo.location_resolve
- `GET /geo/api/v1/geocoding/resolve` → geo.geocode_address, geo.pick_location
- `GET /geo/api/v1/geocoding/reverse` → geo.geocode_address
- `GET /geo/api/v1/geocoding/search` → geo.geocode_address, geo.pick_location
- `GET /geo/api/v1/geocoding/structured` → geo.geocode_address
- `GET /geo/api/v1/map/config` → geo.pick_location
