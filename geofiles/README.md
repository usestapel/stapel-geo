# GADM flattening tool

stapel-geo does **not** ship any bulk geographic data — hosts supply their
own GADM extracts, and none are bundled in the wheel or the repo. This
folder contains only:

- `flatten_hierarchy.py` — the optional GADM level-flattening helper (e.g.
  drop the districts level so cantons attach directly to the country).

The import pipeline itself is exercised in tests against small synthetic
GeoJSON fixtures built in-memory (see `tests/test_models.py`), not against
real GADM data.

## Getting GADM data

Download extracts from [gadm.org](https://gadm.org/) as GeoJSON. Each file's
`name` must end in its depth level (e.g. `gadm41_<ISO3>_2`) — the importer
reads the level from that suffix. Import them lowest-level-first:

```bash
python manage.py load_geofiles --folder /path/to/gadm
```

## Licensing

GADM data is licensed for **non-commercial** use; redistribution requires
permission. See <https://gadm.org/license.html>. Because of this, no GADM
extract — not even a small sample — is shipped. Point
`STAPEL_GEO["GADM_FOLDER"]` (or `--folder`) at your own extracts.
