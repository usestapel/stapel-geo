"""Self-contained test settings for stapel-geo.

Two modes, chosen at import by whether a working GDAL/GEOS stack is present
(``stapel_geo.tests._support.SPATIAL``):

* **Non-spatial (always runs).** ``stapel_geo`` is NOT installed as an app,
  so the GeoDjango models never load and GDAL is never required. The
  GDAL-free layers — geohash math, geocoder seam, comm Functions, conf,
  the GADM import status machine, system checks — are registered by
  importing their modules directly and are fully exercised. Comm handlers
  that would touch the ORM are monkeypatched in the tests.

* **Spatial (only with GDAL, e.g. CI).** ``django.contrib.gis`` +
  ``stapel_geo`` are installed on a SpatiaLite database so the location
  tree / GADM import / HTTP views run too.

Comm runs in-process with ``VALIDATE_SCHEMAS`` on, so the committed
contracts in ``schemas/`` are enforced by the tests.
"""
from stapel_geo.tests._support import SPATIAL

_BASE_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.admin",
    "django.contrib.messages",
    "stapel_core.django.users",
    "rest_framework",
]


def pytest_configure(config):
    from django.conf import settings

    if settings.configured:
        return

    spatialite_path = None
    if SPATIAL:
        installed_apps = _BASE_APPS + ["django.contrib.gis", "stapel_geo"]
        databases = {
            "default": {
                "ENGINE": "django.contrib.gis.db.backends.spatialite",
                "NAME": ":memory:",
            }
        }
        root_urlconf = "stapel_geo.tests.urls"
        # Let Django find the SpatiaLite loadable extension (Debian/Ubuntu
        # ship it as ``mod_spatialite``); a no-op on platforms that autoload.
        spatialite_path = "mod_spatialite"
    else:
        installed_apps = _BASE_APPS
        databases = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        }
        # Only the GDAL-free geocoder proxy is mountable without the app.
        root_urlconf = "stapel_geo.tests.urls_nonspatial"

    settings.configure(
        SECRET_KEY="test-secret-key-not-for-production",
        INSTALLED_APPS=installed_apps,
        AUTH_USER_MODEL="users.User",
        DATABASES=databases,
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        ROOT_URLCONF=root_urlconf,
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        STAPEL_BUS_BACKEND="stapel_core.bus.backends.memory.MemoryBus",
        STAPEL_COMM={
            "OUTBOX_ENABLED": False,
            "ACTION_TRANSPORT": "inprocess",
            "VALIDATE_SCHEMAS": True,
        },
        MIGRATION_MODULES={"users": None, "geo": None},
        SPATIALITE_LIBRARY_PATH=spatialite_path,
    )
    import django

    django.setup()

    # In non-spatial mode the app's ready() never runs (it is not installed),
    # so register the GDAL-free side effects explicitly: error keys, comm
    # Functions + emit schema, and system checks.
    if not SPATIAL:
        import stapel_geo.actions  # noqa: F401  (registers geo.import.completed schema)
        import stapel_geo.checks  # noqa: F401  (registers system checks)
        import stapel_geo.errors  # noqa: F401  (registers error keys)
        import stapel_geo.functions  # noqa: F401  (registers geo.nearby/geo.resolve)

    from stapel_core.comm.schemas import autoload_schemas

    autoload_schemas()


import pytest  # noqa: E402


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()
