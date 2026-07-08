# stapel-geo

[![CI](https://github.com/usestapel/stapel-geo/actions/workflows/ci.yml/badge.svg)](https://github.com/usestapel/stapel-geo/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/usestapel/stapel-geo/graph/badge.svg)](https://codecov.io/gh/usestapel/stapel-geo)
[![PyPI](https://img.shields.io/pypi/v/stapel-geo.svg)](https://pypi.org/project/stapel-geo/)

Geographic locations and geocoding for the [Stapel framework](https://github.com/usestapel) —
composable Django apps that deploy as a monolith or as microservices
without changing module code.

- **Location tree** — hierarchical places (GeoDjango + treenode) with GADM
  boundaries, centroid geohash, and cross-service UUIDs.
- **GADM import** — upload GeoJSON extracts; a status machine streams them
  into the tree with progress + a completion event.
- **Geohash proximity** — nearby-by-coordinates / nearby-by-geohash.
- **Geocoder proxy** — forward / structured / reverse geocoding behind a
  swappable provider seam (Photon by default).

## Install

```bash
pip install stapel-geo              # geohash math, geocoder proxy, comm surface
pip install "stapel-geo[spatial]"   # + the spatial layer (needs GDAL + a spatial DB)
```

The location tree, GADM import and admin need the **GDAL** C library and a
spatial database (PostGIS in production, SpatiaLite for tests). The geohash
math, geocoder proxy, comm Functions and settings work **without** GDAL.

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.gis",   # only if you use the spatial layer
    "stapel_geo",
]

# urls.py
path("geo/", include("stapel_geo.urls"))
# ... or mount only the GDAL-free geocoder proxy:
path("geo/geocoding/", include("stapel_geo.geocoding.urls"))
```

Before the first spatial migration in production:

```bash
python manage.py enable_postgis
python manage.py load_geofiles --folder /path/to/gadm
```

## Settings (`STAPEL_GEO`)

| Key | Default | Meaning |
|---|---|---|
| `GEOCODER` | `…providers.PhotonGeocoder` | Geocoder provider class (dotted path). |
| `PHOTON_URL` | `http://localhost:2322` | Photon base URL (default provider). |
| `PHOTON_LANGUAGES` | `["default","en","de","fr"]` | Indexed languages; others fall back to `en`. |
| `GEOCODER_TIMEOUT` | `10` | Geocoder HTTP timeout (s). |
| `GEOHASH_PRECISION` | `8` | Stored centroid geohash precision. |
| `NEARBY_PRECISION` | `6` | Default precision for coordinate nearby search. |
| `NEARBY_LIMIT` / `NEARBY_MAX_LIMIT` | `10` / `50` | Default / max nearby results. |
| `SIMPLIFY_MAX_POINTS` | `100` | `fast_centroid` simplification budget. |
| `GADM_FOLDER` | `/app/geofiles` | Folder `load_geofiles` scans. |
| `IMPORT_ASYNC` | `True` | Background GADM import + `geo.import.completed` emit. |

## comm surface

| Kind | Name | Contract |
|---|---|---|
| Function | `geo.nearby` | `{lat,lon}`/`{geohash}` `[,limit]` → `{results:[…]}` |
| Function | `geo.resolve` | `{uuid}` → `{found, …}` |
| Action | `geo.import.completed` | `{geofile_id, location_level, feature_count, status}` |

```python
from stapel_core.comm import call
call("geo.nearby", {"lat": 49.61, "lon": 6.13, "limit": 5})
```

## GADM data & geocoder providers

The wheel ships no bundled boundaries or sample extract — **hosts supply
their own GADM data** (see `geofiles/README.md`; non-commercial license).
Swap the geocoder
by implementing the `Geocoder` ABC and setting `STAPEL_GEO["GEOCODER"]`.

See [MODULE.md](MODULE.md) for every fork-free seam.

## Development

```bash
pip install -e . && pip install pytest pytest-django ruff pytest-cov
./setup-hooks.sh
pytest tests/    # spatial tests skip-with-reason without GDAL
```

## License

MIT
