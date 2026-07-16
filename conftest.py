"""Self-contained test settings for stapel-geo.

One mode, no GDAL, no spatial database: since 0.3.0 the module is flat
(``Location`` is lat/lon + geohash), so the full suite — models, HTTP
views, search facade, geocoder proxy, comm surface — runs on in-memory
SQLite everywhere. The former spatial/non-spatial split (and its
25 skips-with-reason) is gone as a class.

Comm runs in-process with ``VALIDATE_SCHEMAS`` on, so the committed
contracts in ``schemas/`` are enforced by the tests.
"""

_BASE_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.admin",
    "django.contrib.messages",
    "stapel_core.django.users",
    "rest_framework",
    "stapel_geo",
]


def pytest_configure(config):
    from django.conf import settings

    if settings.configured:
        return

    settings.configure(
        SECRET_KEY="test-secret-key-not-for-production",
        INSTALLED_APPS=_BASE_APPS,
        AUTH_USER_MODEL="users.User",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        USE_TZ=True,
        ROOT_URLCONF="stapel_geo.tests.urls",
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        STAPEL_BUS_BACKEND="stapel_core.bus.backends.memory.MemoryBus",
        STAPEL_COMM={
            "OUTBOX_ENABLED": False,
            "ACTION_TRANSPORT": "inprocess",
            "VALIDATE_SCHEMAS": True,
        },
        # Wide open by default so ordinary geocoding tests never trip the
        # scoped throttle; the throttle test overrides it downward.
        STAPEL_GEO={"GEOCODER_THROTTLE": "10000/min"},
        MIGRATION_MODULES={"users": None, "geo": None},
    )
    import django

    django.setup()

    from stapel_core.comm.schemas import autoload_schemas

    autoload_schemas()


import pytest  # noqa: E402


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()
