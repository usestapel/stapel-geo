"""Geocoder resolution + the cached, ledgered call path.

``get_geocoder(name)`` resolves a provider **name** through the merge-
registry (``registered_geocoders()``; ``STAPEL_GEO["GEOCODER"]`` names
the default). 0.3.0 breaking: ``GEOCODER`` was a dotted path before.

``geocode(verb, ...)`` is the one call path the HTTP proxy uses: cache
lookup (``GEOCODE_CACHE_POLICY`` seam) -> provider call -> ledger row.
Every call writes a ``GeocodeCache`` accounting row (ok / error /
cache_hit) — spend per provider/verb is always visible to the host.
"""
from __future__ import annotations

import time

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ..conf import geo_settings
from ..models import GeocodeCache
from .base import Geocoder, GeocoderError
from .cache import query_hash, write_ledger
from .dto import GeocodeResponse
from .providers import registered_geocoders


def get_geocoder(name: str | None = None) -> Geocoder:
    """Instantiate the provider registered under *name* (default:
    ``STAPEL_GEO["GEOCODER"]``).

    Raises :class:`~django.core.exceptions.ImproperlyConfigured` when the
    name is not in the registry or does not resolve to a
    :class:`Geocoder` subclass — callers surface this as a 5xx, the
    system checks (``stapel_geo.W001``/``W002``) surface it at deploy time.
    """
    name = name or geo_settings.GEOCODER
    registry = registered_geocoders()
    dotted_path = registry.get(name)
    if not dotted_path:
        raise ImproperlyConfigured(
            f"STAPEL_GEO['GEOCODER'] names {name!r}, which is not a registered "
            f"geocoder (registered: {sorted(registry)}). Add it via "
            "STAPEL_GEO['GEOCODERS'] or register_geocoder()."
        )
    try:
        geocoder_cls = import_string(dotted_path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"Geocoder {name!r} points at {dotted_path!r}, which cannot be "
            f"imported: {exc}"
        ) from exc
    if not (isinstance(geocoder_cls, type) and issubclass(geocoder_cls, Geocoder)):
        raise ImproperlyConfigured(
            f"Geocoder {name!r} ({dotted_path!r}) must be a "
            f"stapel_geo.geocoding.base.Geocoder subclass, got {geocoder_cls!r}"
        )
    return geocoder_cls()


def geocode(verb: str, *, lang: str | None = None, **kwargs) -> GeocodeResponse:
    """Run one geocoding *verb* through cache + provider + ledger.

    ``verb`` is ``"search"`` / ``"reverse"`` / ``"structured"``; ``kwargs``
    are that verb's arguments (positional args of the provider methods are
    passed by name: ``query=...``, ``lat=.../lng=...``). Raises
    :class:`GeocoderError` on provider failure (after the ledger row).
    """
    provider = get_geocoder()
    policy = geo_settings.GEOCODE_CACHE_POLICY()
    qhash = query_hash(verb, {**kwargs, "lang": lang})
    lang_key = lang or ""

    if policy.should_cache(verb):
        cached = policy.lookup(provider.name, verb, qhash, lang_key)
        if cached is not None:
            write_ledger(
                provider=provider.name,
                verb=verb,
                query_hash=qhash,
                lang=lang_key,
                status=GeocodeCache.Status.CACHE_HIT,
                duration_ms=0,
            )
            return cached

    method = getattr(provider, verb)
    started = time.monotonic()
    try:
        if verb == "search":
            response = method(kwargs.pop("query"), lang=lang, **kwargs)
        elif verb == "reverse":
            response = method(kwargs.pop("lat"), kwargs.pop("lng"), lang=lang, **kwargs)
        else:
            response = method(lang=lang, **kwargs)
    except GeocoderError:
        write_ledger(
            provider=provider.name,
            verb=verb,
            query_hash=qhash,
            lang=lang_key,
            status=GeocodeCache.Status.ERROR,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise
    duration_ms = int((time.monotonic() - started) * 1000)

    write_ledger(
        provider=provider.name,
        verb=verb,
        query_hash=qhash,
        lang=lang_key,
        status=GeocodeCache.Status.OK,
        duration_ms=duration_ms,
        response=response,
    )
    if policy.should_cache(verb):
        policy.store(provider.name, verb, qhash, lang_key, response)
    return response


__all__ = ["get_geocoder", "geocode"]
