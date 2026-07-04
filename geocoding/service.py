"""Resolve the configured geocoder (the ``GEOCODER`` dotted-path seam)."""
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from ..conf import geo_settings
from .base import Geocoder


def get_geocoder() -> Geocoder:
    """Instantiate ``STAPEL_GEO["GEOCODER"]`` (a :class:`Geocoder` subclass).

    Raises :class:`~django.core.exceptions.ImproperlyConfigured` when the
    configured path does not resolve to a ``Geocoder`` subclass — callers
    surface this as a 5xx, the system check (checks.W001/W002) surfaces it
    at deploy time.
    """
    geocoder_cls = geo_settings.GEOCODER
    if not (isinstance(geocoder_cls, type) and issubclass(geocoder_cls, Geocoder)):
        raise ImproperlyConfigured(
            "STAPEL_GEO['GEOCODER'] must point to a "
            f"stapel_geo.geocoding.base.Geocoder subclass, got {geocoder_cls!r}"
        )
    return geocoder_cls()


__all__ = ["get_geocoder"]
