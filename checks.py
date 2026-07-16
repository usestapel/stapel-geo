"""Django system checks for stapel-geo configuration.

Policy (docs/library-standard.md §3.7): E-level for configuration the
service cannot run with; W-level for entries that degrade lazily. Both
seams here are W-level — the location tree works without a working
geocoder, and a broken search backend only breaks the search verbs — so
a bad value must not block deploys, only warn.

- ``stapel_geo.W001`` — ``GEOCODER`` names an unregistered provider, or
  its registry entry fails to import.
- ``stapel_geo.W002`` — the ``GEOCODER`` entry resolves to a
  non-``Geocoder`` class.
- ``stapel_geo.W003`` — ``SEARCH_BACKEND`` dotted path fails to import.
- ``stapel_geo.W004`` — ``SEARCH_BACKEND`` resolves to a class missing
  the facade verbs (nearby/radius/bbox).
"""
from __future__ import annotations

import inspect

from django.core import checks


@checks.register("stapel_geo")
def check_geocoder(app_configs, **kwargs):
    from django.utils.module_loading import import_string

    from .conf import geo_settings
    from .geocoding.base import Geocoder
    from .geocoding.providers import registered_geocoders

    name = geo_settings.GEOCODER
    registry = registered_geocoders()
    dotted_path = registry.get(name)
    if not dotted_path:
        return [
            checks.Warning(
                f"STAPEL_GEO['GEOCODER'] names {name!r}, which is not a registered "
                f"geocoder (registered: {sorted(registry)}).",
                hint="Add it via STAPEL_GEO['GEOCODERS'] or register_geocoder(); "
                     "the geocoder proxy will fail until it resolves.",
                id="stapel_geo.W001",
            )
        ]
    try:
        geocoder = import_string(dotted_path)
    except ImportError as exc:
        return [
            checks.Warning(
                f"Geocoder {name!r} ({dotted_path!r}) cannot be imported: {exc}",
                hint="Fix the dotted path or install the missing dependency; "
                     "the geocoder proxy will fail until it resolves.",
                id="stapel_geo.W001",
            )
        ]
    if not (inspect.isclass(geocoder) and issubclass(geocoder, Geocoder)):
        return [
            checks.Warning(
                f"Geocoder {name!r} resolves to {geocoder!r}, which is not a "
                "stapel_geo.geocoding.base.Geocoder subclass.",
                hint="Implement the Geocoder ABC (see MODULE.md).",
                id="stapel_geo.W002",
            )
        ]
    return []


@checks.register("stapel_geo")
def check_search_backend(app_configs, **kwargs):
    from .conf import geo_settings

    try:
        backend = geo_settings.SEARCH_BACKEND
    except ImportError as exc:
        return [
            checks.Warning(
                f"STAPEL_GEO['SEARCH_BACKEND'] cannot be imported: {exc}",
                hint="Fix the dotted path or install the missing dependency; "
                     "nearby/radius/bbox will fail until it resolves.",
                id="stapel_geo.W003",
            )
        ]
    verbs = ("nearby", "radius", "bbox")
    if not inspect.isclass(backend) or not all(
        callable(getattr(backend, verb, None)) for verb in verbs
    ):
        return [
            checks.Warning(
                f"STAPEL_GEO['SEARCH_BACKEND'] resolves to {backend!r}, which does "
                "not implement the GeoSearchBackend protocol (nearby/radius/bbox).",
                hint="Implement stapel_geo.search.base.GeoSearchBackend (see MODULE.md).",
                id="stapel_geo.W004",
            )
        ]
    return []


__all__ = ["check_geocoder", "check_search_backend"]
