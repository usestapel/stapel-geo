"""Import GADM GeoJSON extracts from a folder into the location tree.

The folder defaults to ``STAPEL_GEO["GADM_FOLDER"]`` (override with
``--folder``). Files are imported in filename order so lower GADM levels
(countries) land before their children. Hosts supply their own GADM
extracts — none are shipped in the wheel (see MODULE.md for licensing).
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand

from ...conf import geo_settings
from ...imports import ImportStatus
from ...models import GeoFile


class Command(BaseCommand):
    help = "Load GADM GeoJSON files from a folder into the location tree."

    def add_arguments(self, parser):
        parser.add_argument("--folder", type=str, default=None,
                            help="Folder with GeoJSON files (default: STAPEL_GEO['GADM_FOLDER']).")
        parser.add_argument("--force", action="store_true",
                            help="Import even if GeoFiles already exist.")

    def handle(self, *args, **options):
        folder = Path(options["folder"] or geo_settings.GADM_FOLDER)
        force = options["force"]

        if GeoFile.objects.exists() and not force:
            self.stdout.write(self.style.SUCCESS("GeoFiles already present; skipping (use --force)."))
            return
        if not folder.exists():
            self.stdout.write(self.style.WARNING(f"Folder {folder} does not exist; skipping."))
            return

        if force:
            # Clear prior GeoFile rows (and their stored files) so repeated
            # --force runs re-import cleanly instead of piling up duplicate
            # GeoFile rows. Locations are upserted by g_id and survive.
            stale = list(GeoFile.objects.all())
            for gf in stale:
                gf.geo_json.delete(save=False)
                gf.delete()
            if stale:
                self.stdout.write(f"Removed {len(stale)} existing GeoFile record(s) before re-import.")

        files = sorted(list(folder.glob("*.geojson")) + list(folder.glob("*.json")),
                       key=lambda f: f.name)
        if not files:
            self.stdout.write(self.style.WARNING(f"No GeoJSON files in {folder}; skipping."))
            return

        self.stdout.write(f"Found {len(files)} file(s) to import...")
        ok = err = 0
        for path in files:
            self.stdout.write(f"  Importing {path.name}...")
            try:
                with open(path, "rb") as fh:
                    geofile = GeoFile.create_and_import_sync(geo_json=File(fh, name=path.name))
                if geofile.import_status == ImportStatus.COMPLETED:
                    self.stdout.write(self.style.SUCCESS(f"    OK - level {geofile.location_level}"))
                    ok += 1
                else:
                    self.stdout.write(self.style.ERROR(f"    Error: {geofile.import_error}"))
                    err += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"    Failed: {exc}"))
                err += 1

        style = self.style.SUCCESS if err == 0 else self.style.WARNING
        self.stdout.write(style(f"Import complete: {ok} ok, {err} error(s)."))
