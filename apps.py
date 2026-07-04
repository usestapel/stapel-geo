from django.apps import AppConfig


class GeoConfig(AppConfig):
    name = "stapel_geo"
    label = "geo"
    verbose_name = "Geographic locations and geocoding"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Import-time side effects: comm functions/actions, system checks,
        # error-key registration. Keep each in its own module. None of these
        # import GDAL — only models/views/admin do.
        from . import actions  # noqa: F401
        from . import checks  # noqa: F401
        from . import errors  # noqa: F401
        from . import functions  # noqa: F401
