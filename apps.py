from django.apps import AppConfig


class GeoConfig(AppConfig):
    name = "stapel_geo"
    label = "geo"
    verbose_name = "Geographic locations and geocoding"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import-time side effects: comm functions, system checks, error-key
        # registration, flows. Keep each in its own module.
        from . import checks  # noqa: F401
        from . import errors  # noqa: F401
        from . import flows  # noqa: F401
        from . import functions  # noqa: F401

        self._connect_redis_side_index()

    def _connect_redis_side_index(self):
        """Mirror Location writes into Redis when that backend is configured.

        The receivers are connected unconditionally but no-op unless the
        resolved SEARCH_BACKEND is the Redis one (checked per signal, so a
        settings override in tests behaves predictably). Postgres stays the
        source of truth; a missed write is recoverable via ``rebuild()``.
        """
        from django.db.models.signals import post_delete, post_save

        from .models import Location
        from .search.redis import remove_location, sync_location

        post_save.connect(sync_location, sender=Location, dispatch_uid="geo_redis_sync")
        post_delete.connect(
            remove_location, sender=Location, dispatch_uid="geo_redis_remove"
        )
