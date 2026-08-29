"""The IP-geolocation provider seam.

Subclass :class:`IpLocator`, implement :meth:`locate`, and name it in
``STAPEL_GEO["IP_LOCATORS"]`` (or :func:`register_ip_locator`) to swap the
backend without forking::

    class AcmeIpLocator(IpLocator):
        name = "acme"

        def locate(self, ip):
            ...  # -> IpLocation | None

    STAPEL_GEO = {
        "IP_LOCATORS": {"acme": "myproject.geo.AcmeIpLocator"},
        "IP_LOCATOR": "acme",
    }

Contract, and the two halves of it that are easy to get wrong:

- **"I do not know" is a return value, not an exception.** A private
  address, a range the database has never heard of, a loopback request in
  development — none of those is a fault, and every one of them is the
  normal case somewhere. Return ``None`` and the service applies the
  configured fallback centre.
- :class:`IpLocatorError` is for a genuinely broken backend (a missing
  database file, an unreachable upstream). The service catches it, logs
  it, and *still* falls back — because a map that will not open is a worse
  outcome than a map that opens in the wrong city.

Implementations read configuration lazily (at call time, via
``geo_settings``) and keep ``__init__`` cheap: they are instantiated per
call, exactly like geocoders.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from .dto import IpLocation


class IpLocatorError(Exception):
    """The IP-geolocation backend is unusable (missing data, unreachable)."""


class IpLocator(ABC):
    """Base class for IP-geolocation providers."""

    #: Short human-readable provider name ("maxmind", "static", ...).
    name: str = ""

    @abstractmethod
    def locate(self, ip: str) -> Optional[IpLocation]:
        """Best guess for *ip*, or ``None`` when there is none to give."""


__all__ = ["IpLocator", "IpLocatorError"]
