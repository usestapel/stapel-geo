"""Locator resolution + the call path that always answers.

``locate_ip(ip)`` is the one entry point the HTTP view uses. It resolves
the configured provider by name, asks it, and — when the answer is
``None`` or the provider is broken — applies the configured fallback
centre. It does not raise for an unknown address, because "we could not
place this visitor" is the ordinary case and a picker still has to open.

The result is cached per address for ``IP_CACHE_TTL_S`` seconds. An IP's
city does not change between two page loads, and the cache is what keeps a
storefront's search page from doing a database lookup per visitor per
navigation.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from ..conf import geo_settings
from .base import IpLocator, IpLocatorError
from .dto import IpLocation
from .providers import registered_ip_locators

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "stapel_geo:ipgeo:"


def get_ip_locator(name: str | None = None) -> IpLocator:
    """Instantiate the locator registered under *name*.

    Default: ``STAPEL_GEO["IP_LOCATOR"]``. Raises
    :class:`~django.core.exceptions.ImproperlyConfigured` for an unknown
    name or a non-:class:`IpLocator` entry; ``stapel_geo.W008``/``W009``
    surface the same two faults at deploy time.
    """
    name = name or geo_settings.IP_LOCATOR
    registry = registered_ip_locators()
    dotted_path = registry.get(name)
    if not dotted_path:
        raise ImproperlyConfigured(
            f"STAPEL_GEO['IP_LOCATOR'] names {name!r}, which is not a registered "
            f"IP locator (registered: {sorted(registry)}). Add it via "
            "STAPEL_GEO['IP_LOCATORS'] or register_ip_locator()."
        )
    try:
        locator_cls = import_string(dotted_path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"IP locator {name!r} points at {dotted_path!r}, which cannot be "
            f"imported: {exc}"
        ) from exc
    if not (isinstance(locator_cls, type) and issubclass(locator_cls, IpLocator)):
        raise ImproperlyConfigured(
            f"IP locator {name!r} ({dotted_path!r}) must be a "
            f"stapel_geo.ipgeo.base.IpLocator subclass, got {locator_cls!r}"
        )
    return locator_cls()


def fallback_location() -> Optional[IpLocation]:
    """The centre to open on when nothing is known about the caller.

    ``IP_FALLBACK_CENTER``, or ``MAP_DEFAULT_CENTER`` when it is unset —
    the map's opening centre is already the deployment's answer to "where
    does this product live", and making a second setting mandatory to
    restate it is how the two drift apart.
    """
    center = geo_settings.IP_FALLBACK_CENTER or geo_settings.MAP_DEFAULT_CENTER
    if not center or len(center) != 2:
        return None
    return IpLocation(
        lat=float(center[0]),
        lon=float(center[1]),
        source="fallback",
        precision="default",
        ip_resolved=False,
        label=geo_settings.IP_FALLBACK_LABEL or None,
    )


def _cache_key(ip: str, name: str) -> str:
    digest = hashlib.sha256(f"{name}:{ip}".encode()).hexdigest()[:32]
    return f"{_CACHE_PREFIX}{digest}"


def locate_ip(ip: str | None, *, use_cache: bool = True) -> Optional[IpLocation]:
    """Place *ip*, or return the fallback centre. Never raises for input.

    ``None`` comes back only when the locator had no answer AND no
    fallback centre is configured — i.e. the deployment has genuinely
    declined to have an opinion, which a caller renders as "choose a
    place" rather than as an error.
    """
    name = geo_settings.IP_LOCATOR
    if not ip or not name:
        return fallback_location()

    key = _cache_key(ip, name)
    if use_cache:
        cached = cache.get(key)
        if cached is not None:
            return cached or fallback_location()

    result: Optional[IpLocation] = None
    try:
        result = get_ip_locator(name).locate(ip)
    except (IpLocatorError, ImproperlyConfigured) as exc:
        # A broken backend must not take the map down with it — log it
        # (loudly enough for an operator, once per call) and fall back.
        logger.warning("IP locator %r unusable: %s", name, exc)
    except Exception:  # noqa: BLE001 - a provider bug is still not a 500 here
        logger.exception("IP locator %r raised while locating an address", name)

    if use_cache:
        ttl = int(geo_settings.IP_CACHE_TTL_S or 0)
        if ttl > 0:
            # `False` records a known-negative so a miss is not re-looked-up
            # on every page load; the fallback is applied on read, not
            # stored, so moving MAP_DEFAULT_CENTER takes effect at once.
            cache.set(key, result if result is not None else False, ttl)

    return result if result is not None else fallback_location()


__all__ = ["get_ip_locator", "locate_ip", "fallback_location"]
