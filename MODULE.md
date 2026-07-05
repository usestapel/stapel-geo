# stapel-geo — MODULE.md

> Agent-facing map of this module: what it provides, where to extend it
> without forking, and what not to do. Kept in the same PR as any change
> to a seam. See also README.md and CHANGELOG.md.

## What this module provides

- **Location tree** (`models.Location`, GeoDjango + `django-treenode`):
  hierarchical places with GADM boundary geometry, a simplified centroid
  (`fast_centroid`), an indexed centroid **geohash**, and a stable
  cross-service **UUID**.
- **GADM import** (`models.GeoFile` + `imports.GeoFileImporter`): upload a
  GADM GeoJSON extract, validate it, and stream its features into the tree
  with a `pending → processing → completed/failed` status machine and
  progress tracking. Management commands `enable_postgis` and
  `load_geofiles`.
- **Geohash proximity search** (`geohash.py`, pure): nearby-by-coords and
  nearby-by-geohash via index-friendly prefix expansion over the target cell
  **and its 8 neighbours**, ranked by true haversine `distance_km`, with an
  authoritative full-scan fallback so nearest neighbours across a cell
  boundary, the equator, the antimeridian or a pole are not lost. Exposed
  over HTTP and as the `geo.nearby` comm Function.
- **Geocoder proxy** (`geocoding/`): forward / structured / reverse
  geocoding behind a swappable **provider seam** (Photon by default),
  JWT-guarded, returning a normalized GeoJSON `GeocodeResponse`.
- **comm surface**: Functions `geo.nearby` / `geo.resolve` (so listings and
  calendar/booking query geo by name, never importing it) and the
  `geo.import.completed` Action.

### GDAL-optional structure (important)

Only `models.py`, `views.py`, `serializers.py`, `admin.py` and the spatial
management command import **GDAL/GeoDjango**. Everything else — `geohash`,
`geocoding/*`, `functions`, `actions`, `services`, `conf`, `errors`,
`checks`, `imports` — is **GDAL-free** and importable without a spatial
stack. `import stapel_geo` is Django-free and GDAL-free (PEP 562 lazy
exports). This lets tooling, the geocoder proxy, the geohash math and the
comm surface run where GDAL is unavailable; only the location tree / GADM
import / spatial HTTP views require the `geo` extra + a spatial DB.

The initial spatial migration (`migrations/0001_initial.py`) is committed —
`Location`/`GeoFile` with SRID-4326 geometry columns and the indexed centroid
geohash. It applies on PostGIS (production; run `enable_postgis` first) and on
SpatiaLite. CI installs `gdal-bin libgdal-dev libgeos-dev
libsqlite3-mod-spatialite` and runs the full spatial suite against in-memory
SpatiaLite (geometry columns register correctly there — no PostGIS service
needed for CI). `djangorestframework-gis` is **not** required: geometry is
serialized as GeoJSON via method fields.

## Extension points (fork-free)

### Settings — `STAPEL_GEO` namespace (`conf.py`)

Resolution per key: `settings.STAPEL_GEO[key]` → flat Django setting → env
var → default. Read lazily at call time.

| Key | Default | What it customizes | Semantics |
|---|---|---|---|
| `GEOCODER` | `stapel_geo.geocoding.providers.PhotonGeocoder` | Geocoder provider class (dotted path). | **REPLACE** (single strategy) |
| `PHOTON_URL` | `http://localhost:2322` | Base URL of the Photon instance the default provider proxies. | value |
| `PHOTON_LANGUAGES` | `["default","en","de","fr"]` | Languages the Photon bundle indexes; others fall back to `en`. | value |
| `GEOCODER_TIMEOUT` | `10` | HTTP timeout (s) for geocoder calls. | value |
| `GEOHASH_PRECISION` | `8` | Geohash precision stored on `Location.center`. | value |
| `NEARBY_PRECISION` | `6` | Default geohash precision for coordinate nearby search. | value |
| `NEARBY_LIMIT` / `NEARBY_MAX_LIMIT` | `10` / `50` | Default / max nearby result count. | value |
| `SIMPLIFY_MAX_POINTS` | `100` | `fast_centroid` simplification budget. | value |
| `GADM_FOLDER` | `/app/geofiles` | Folder `load_geofiles` scans. | value |
| `IMPORT_ASYNC` | `True` | Run GADM imports in a background thread + emit `geo.import.completed`. | value |

### Geocoder provider seam — `GEOCODER` (ABC: `geocoding/base.py`)

`STAPEL_GEO["GEOCODER"]` is a **REPLACE** dotted-path seam. Implement the
`Geocoder` ABC to add Nominatim / Google / Mapbox / etc. without forking:

```python
from stapel_geo.geocoding.base import Geocoder
from stapel_geo.geocoding.dto import GeocodeResponse

class NominatimGeocoder(Geocoder):
    name = "nominatim"
    def search(self, query, *, lang=None, limit=None, **params) -> GeocodeResponse: ...
    def reverse(self, lat, lng, *, lang=None, limit=None, **params) -> GeocodeResponse: ...
    def structured(self, *, lang=None, limit=None, **params) -> GeocodeResponse: ...

STAPEL_GEO = {"GEOCODER": "myproject.geo.NominatimGeocoder"}
```

Contract: each verb returns a normalized `GeocodeResponse` (GeoJSON
FeatureCollection) and raises `GeocoderError` when the upstream is
unreachable (surfaced as HTTP 502 `error.502.geocoder_unavailable`).
Read config lazily via `geo_settings`; never import GDAL. `checks.W001/W002`
warn (not error — geocoding is degradable) if the path is broken.

### Serializer seams (`views.py`, `geocoding/views.py`)

`seams.SerializerSeamMixin` — subclass a geocoder view, set
`response_serializer_class`, remount the URL. The Location/GeoFile views are
DRF `ModelViewSet`s: swap `serializer_class` / `get_serializer_class` in a
subclass and remount.

| View | Response serializer |
|---|---|
| `GeocodeSearchView` / `GeocodeReverseView` / `GeocodeStructuredView` | `GeocodeResponseSerializer` |
| `LocationViewSet` | `LocationSerializer` / `LocationCompactSerializer` (list, nearby) |
| `GeoFileViewSet` | `GeoFileSerializer` |

### GADM feature importer seam (`imports.GeoFileImporter`)

The status machine is GDAL-free and takes an injected
`feature_importer(level, feature)` callable (the model wires in the
GDAL-backed `models.import_feature`). Reuse `GeoFileImporter` with your own
importer for a non-GADM source, or subclass `GeoFile` to change the pipeline.

### comm surface

| Kind | Name | Payload → Result | Schema |
|---|---|---|---|
| Function (provides) | `geo.nearby` | `{lat,lon[,precision]}` or `{geohash}` `[,limit]` → `{results:[{uuid,name,country,geohash,distance_km}]}` | `schemas/functions/geo.nearby.json` |
| Function (provides) | `geo.resolve` | `{uuid}` → `{found,uuid[,name,country,type,display_name]}` | `schemas/functions/geo.resolve.json` |
| Action (emits) | `geo.import.completed` | `{geofile_id,location_level,feature_count,status}` | `schemas/emits/geo.import.completed.json` |

Emitted only on the async import path (`IMPORT_ASYNC=True`). Subscribers
(search reindex, caches) must be idempotent — at-least-once delivery.

## Hosts supply their own GADM data

The wheel ships **only** a tiny sample (`geofiles/gadm41_LUX_0.json`) plus
the flattening helper — not bulk boundaries. GADM data is non-commercial-
licensed and large; download your own extracts from
[gadm.org](https://gadm.org/) and point `STAPEL_GEO["GADM_FOLDER"]` (or
`load_geofiles --folder`) at them. Each file's `name` must end in its depth
level (`gadm41_LUX_2`).

## GDPR

No GDPR consumer is needed: locations are **reference data**, not user PII.
`Location.uuid` is a cross-service reference for a place, not a person; the
module stores no `AUTH_USER_MODEL` rows and subscribes to no `user.deleted`.

## Anti-patterns

- **Don't fork to change the geocoder** — implement the `Geocoder` ABC and
  set `GEOCODER`.
- **Don't import GDAL in the GDAL-free layers** — keep `geohash`,
  `geocoding`, `functions`, `services`, `imports` importable without a
  spatial stack (a subprocess test enforces it). Import `Location`/`GeoFile`
  only where you truly need geometry, and lazily.
- **Don't import other stapel modules** — listings/calendar reach geo via
  `geo.nearby` / `geo.resolve` (comm-by-name), never `import stapel_geo` in
  another module.
- **Don't bypass the settings namespace** with `os.getenv` at import time.
- **Don't ship bulk GADM data** in the package.

## App-layer override vs upstream contribution — rule of thumb

**App-layer** (host project, no fork): a new geocoder provider via the
`GEOCODER` seam, a settings value, a view subclass + URL remount, a
`geo.import.completed` subscriber.

**Upstream contribution**: new model fields/migrations, a new endpoint, a
new settings key or seam, or a change to a committed schema.

Litmus test: if you'd have to monkeypatch or edit code inside
`stapel_geo/` — it's upstream. If a setting, subclass, receiver or comm
call gets you there — it's app-layer.
