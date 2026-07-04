"""Django system checks for stapel-geo configuration.

Policy (docs/library-standard.md §3.7): E-level for configuration the
service cannot run with; W-level for entries that degrade lazily. The
geocoder is W-level — the location tree and imports work fine without a
working geocoder, so a bad ``GEOCODER`` must not block deploys, only warn.

- ``stapel_geo.W001`` — ``GEOCODER`` dotted path fails to import.
- ``stapel_geo.W002`` — ``GEOCODER`` resolves to a non-``Geocoder``.
"""
from __future__ import annotations

import inspect

from django.core import checks


@checks.register("stapel_geo")
def check_geocoder(app_configs, **kwargs):
    from .conf import geo_settings
    from .geocoding.base import Geocoder

    try:
        geocoder = geo_settings.GEOCODER
    except ImportError as exc:
        return [
            checks.Warning(
                f"STAPEL_GEO['GEOCODER'] cannot be imported: {exc}",
                hint="Fix the dotted path or install the missing dependency; "
                     "the geocoder proxy will fail until it resolves.",
                id="stapel_geo.W001",
            )
        ]
    if not (inspect.isclass(geocoder) and issubclass(geocoder, Geocoder)):
        return [
            checks.Warning(
                f"STAPEL_GEO['GEOCODER'] resolves to {geocoder!r}, which is not a "
                "stapel_geo.geocoding.base.Geocoder subclass.",
                hint="Implement the Geocoder ABC (see MODULE.md).",
                id="stapel_geo.W002",
            )
        ]
    return []


__all__ = ["check_geocoder"]
