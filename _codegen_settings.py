"""Single-module Django settings for stapel-geo's contract harness.

The pytest suite keeps its own ``conftest.py`` configure block (historical
test config, no drf-spectacular); this file exists only for contract
emission (``_codegen.py`` / ``make contract``): a ``{geo + core}`` instance
mounted at the canonical ``/geo/api/v1/`` prefix with the *production*
``REST_FRAMEWORK`` (the canonical stapel-core config, inlined as dotted
paths — importing it at configure() time would freeze DRF defaults), so
the emitted ``schema.json`` / ``flows.json`` paths are byte-identical to a
monolith aggregate's geo slice (contract-pipeline.md §2).
"""
from __future__ import annotations


def settings_kwargs(*, root_urlconf: str = "stapel_geo.codegen_urls") -> dict:
    """Return the ``settings.configure(**kwargs)`` for the codegen instance."""
    installed_apps = [
        "django.contrib.contenttypes",
        "django.contrib.auth",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.admin",
        # CommonDjangoConfig ships the stapel_core management commands
        # (generate_flow_docs / generate_error_keys used by the emitters).
        "stapel_core.django.apps.CommonDjangoConfig",
        "stapel_core.django.users",
        "rest_framework",
        "drf_spectacular",
        "stapel_geo",
    ]

    # Mirror stapel_core.django.settings.REST_FRAMEWORK (the config the
    # monolith emits under). Inlined, not imported, to dodge the import-time
    # settings read (contract-pipeline.md §3, the billing/auth recipe).
    rest_framework = {
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "stapel_core.django.jwt.authentication.JWTCookieAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "stapel_core.django.api.permissions.IsServiceRequest",
            "stapel_core.django.api.permissions.IsSuperUser",
        ],
        "DEFAULT_RENDERER_CLASSES": [
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        ],
        "DEFAULT_SCHEMA_CLASS": "stapel_core.django.openapi.schemas.PermissionAwareAutoSchema",
        "EXCEPTION_HANDLER": "stapel_core.django.api.errors.stapel_exception_handler",
    }

    return dict(
        SECRET_KEY="codegen-not-a-real-secret",
        INSTALLED_APPS=installed_apps,
        AUTH_USER_MODEL="users.User",
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            }
        },
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
        REST_FRAMEWORK=rest_framework,
    )


# drf-spectacular derives the operationId prefix from the common path of all
# endpoints — "/" across a multi-module monolith, but "/geo/api/v1" in a
# single-module harness (which would strip the mount from operationIds). Pin
# it to the monolith's common prefix so operationIds match the aggregate
# slice byte-for-byte. Uniform across all pair-backends.
CODEGEN_SCHEMA_PATH_PREFIX = "/"
