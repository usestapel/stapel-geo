"""Built-in IP locators + the provider merge-registry.

Registry semantics are the geocoder's, one namespace over:
``registered_ip_locators()`` = ``BUILTIN_IP_LOCATORS`` <- ``STAPEL_GEO
["IP_LOCATORS"]`` (settings merge; ``None``/``""`` removes a name) <-
:func:`register_ip_locator` runtime registrations. ``STAPEL_GEO
["IP_LOCATOR"]`` selects the default **name**.

Built-ins:

- ``maxmind`` — :class:`MaxMindIpLocator`, an offline MaxMind/GeoLite2
  City database. The only built-in that actually knows anything, and the
  reason this seam is worth having: it answers from a file, so no third
  party is told who visits the site and no request is metered.
- ``static`` — :class:`StaticIpLocator`, one configured point for every
  caller. A city-scoped marketplace has one honest answer and this is it.

This module imports nothing heavier than the standard library at import
time; ``geoip2`` is imported inside the call.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import threading
from typing import Optional

from ..conf import geo_settings
from .base import IpLocator, IpLocatorError
from .dto import IpLocation, build_label

logger = logging.getLogger(__name__)


def is_public_ip(ip: str) -> bool:
    """Whether *ip* is an address a locator could plausibly know.

    Loopback, link-local, private and reserved ranges are the addresses a
    request carries in development, behind a misconfigured proxy, or from
    a container network — asking a geolocation database about them wastes
    a lookup to learn nothing.
    """
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return address.is_global


# ---------------------------------------------------------------------------
# MaxMind / GeoLite2 (offline)
# ---------------------------------------------------------------------------


class MaxMindIpLocator(IpLocator):
    """Read an offline MaxMind City database (GeoLite2 or GeoIP2).

    ``STAPEL_GEO["IP_MAXMIND_DB"]`` is the path to the ``.mmdb`` file.
    There is no default, and there is no bundled database: MaxMind's terms
    require an account to download GeoLite2 and forbid redistributing it,
    which is the same discipline the paid geocoders and the LLM providers
    are under — the host brings its own.

    The reader is opened once per path and cached for the process. A
    memory-mapped mmdb reader is thread-safe for reads and re-opening one
    per request would burn the mmap on every page load.
    """

    name = "maxmind"

    _readers: dict[str, object] = {}
    _lock = threading.Lock()

    @classmethod
    def _reader(cls, path: str):
        reader = cls._readers.get(path)
        if reader is not None:
            return reader
        with cls._lock:
            reader = cls._readers.get(path)
            if reader is not None:
                return reader
            try:
                import geoip2.database
            except ImportError as exc:  # pragma: no cover - depends on env
                raise IpLocatorError(
                    "The 'maxmind' IP locator needs the geoip2 package: "
                    "pip install 'stapel-geo[ipgeo]'"
                ) from exc
            if not path:
                raise IpLocatorError(
                    "STAPEL_GEO['IP_MAXMIND_DB'] is empty — the 'maxmind' IP "
                    "locator has no database to read."
                )
            if not os.path.exists(path):
                raise IpLocatorError(
                    f"STAPEL_GEO['IP_MAXMIND_DB'] points at {path!r}, which does "
                    "not exist."
                )
            reader = geoip2.database.Reader(path)
            cls._readers[path] = reader
            return reader

    @classmethod
    def reset(cls) -> None:
        """Drop cached readers (settings changed, tests, a database swap)."""
        with cls._lock:
            for reader in cls._readers.values():
                close = getattr(reader, "close", None)
                if callable(close):
                    close()
            cls._readers.clear()

    def locate(self, ip: str) -> Optional[IpLocation]:
        if not is_public_ip(ip):
            return None
        reader = self._reader(geo_settings.IP_MAXMIND_DB or "")
        try:
            import geoip2.errors

            response = reader.city(ip)  # type: ignore[attr-defined]
        except geoip2.errors.AddressNotFoundError:
            return None
        except Exception as exc:  # noqa: BLE001 - any reader fault is "unusable"
            raise IpLocatorError(f"MaxMind lookup failed for {ip!r}: {exc}") from exc

        location = response.location
        if location is None or location.latitude is None or location.longitude is None:
            return None

        city = _name_of(getattr(response, "city", None))
        region = _name_of(_first(getattr(response, "subdivisions", None)))
        country = _name_of(getattr(response, "country", None))
        country_code = getattr(getattr(response, "country", None), "iso_code", None)
        radius = getattr(location, "accuracy_radius", None)

        return IpLocation(
            lat=float(location.latitude),
            lon=float(location.longitude),
            source=self.name,
            precision="city" if city else ("region" if region else "country"),
            ip_resolved=True,
            label=build_label(city, region, country),
            city=city,
            region=region,
            country=country,
            country_code=country_code,
            accuracy_radius_km=float(radius) if radius is not None else None,
        )


def _first(sequence):
    try:
        return sequence[0]
    except (TypeError, IndexError, KeyError):
        return None


def _name_of(record) -> Optional[str]:
    """The record's own name, preferring the localized dict when present."""
    if record is None:
        return None
    name = getattr(record, "name", None)
    if name:
        return str(name)
    names = getattr(record, "names", None) or {}
    for key in ("en",):
        if names.get(key):
            return str(names[key])
    for value in names.values():
        if value:
            return str(value)
    return None


# ---------------------------------------------------------------------------
# Static (one point, deliberately)
# ---------------------------------------------------------------------------


class StaticIpLocator(IpLocator):
    """Answer every caller with ``STAPEL_GEO["IP_STATIC_POINT"]``.

    ``IP_STATIC_POINT`` is ``[lat, lon]``, optionally with a label in
    ``IP_STATIC_LABEL``. Unset, the locator returns ``None`` and the
    service's fallback centre answers instead — which is the same point a
    deployment would have configured here anyway, so an unconfigured
    ``static`` degrades to the map's own default rather than to nothing.
    """

    name = "static"

    def locate(self, ip: str) -> Optional[IpLocation]:
        point = geo_settings.IP_STATIC_POINT
        if not point or len(point) != 2:
            return None
        label = geo_settings.IP_STATIC_LABEL or None
        return IpLocation(
            lat=float(point[0]),
            lon=float(point[1]),
            source=self.name,
            precision=geo_settings.IP_STATIC_PRECISION or "city",
            ip_resolved=False,
            label=label,
            city=label,
        )


BUILTIN_IP_LOCATORS: dict[str, str] = {
    "maxmind": "stapel_geo.ipgeo.providers.MaxMindIpLocator",
    "static": "stapel_geo.ipgeo.providers.StaticIpLocator",
}

_runtime_ip_locators: dict[str, str | None] = {}


def register_ip_locator(name: str, dotted_path: str | None) -> None:
    """Register (or, with ``None``/``""``, unregister) a locator at runtime."""
    _runtime_ip_locators[name] = dotted_path


def registered_ip_locators() -> dict[str, str]:
    """The effective name -> dotted-path registry."""
    merged: dict[str, str | None] = dict(BUILTIN_IP_LOCATORS)
    merged.update(geo_settings.IP_LOCATORS or {})
    merged.update(_runtime_ip_locators)
    return {name: path for name, path in merged.items() if path}


__all__ = [
    "MaxMindIpLocator",
    "StaticIpLocator",
    "BUILTIN_IP_LOCATORS",
    "register_ip_locator",
    "registered_ip_locators",
    "is_public_ip",
]
