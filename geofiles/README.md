# Sample GADM extract & flattening tool

stapel-geo does **not** ship bulk geographic data — hosts supply their own
GADM extracts. This folder contains only:

- `gadm41_LUX_0.json` — a small sample (Luxembourg, level 0 / country) so
  the import pipeline can be exercised end-to-end without a large download.
- `flatten_hierarchy.py` — the optional GADM level-flattening helper (e.g.
  drop the districts level so cantons attach directly to the country).

## Getting GADM data

Download extracts from [gadm.org](https://gadm.org/) as GeoJSON. Each file's
`name` must end in its depth level (e.g. `gadm41_LUX_2`) — the importer reads
the level from that suffix. Import them lowest-level-first:

```bash
python manage.py load_geofiles --folder /path/to/gadm
```

## Licensing

GADM data is licensed for **non-commercial** use; redistribution requires
permission. See <https://gadm.org/license.html>. Because of this — and to
keep the wheel small — only the tiny sample above is shipped. Point
`STAPEL_GEO["GADM_FOLDER"]` (or `--folder`) at your own extracts.
