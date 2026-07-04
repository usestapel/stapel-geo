"""Enable the PostGIS extension on the configured PostgreSQL database.

Run once before the first spatial migration in production. No-op-safe
(``IF NOT EXISTS``). Requires a PostgreSQL backend with PostGIS available.
"""
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Enable the PostGIS extension and show its version."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
                self.stdout.write(self.style.SUCCESS("PostGIS extension enabled (or already present)."))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"Failed to enable PostGIS: {exc}"))
                return
            try:
                cursor.execute("SELECT PostGIS_Full_Version();")
                version = cursor.fetchone()[0]
                self.stdout.write(self.style.SUCCESS(f"PostGIS version: {version}"))
            except Exception as exc:
                self.stderr.write(
                    self.style.WARNING(f"PostGIS enabled, but version query failed: {exc}")
                )
