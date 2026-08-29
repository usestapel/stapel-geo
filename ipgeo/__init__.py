"""Where the visitor probably is, before they have told anyone.

A location picker has a chicken-and-egg problem: it needs a centre before
it has a location. The browser's own prompt answers it — but only after
the person says yes, and "no" is a supported answer, not an error. Denied,
dismissed, an insecure context, an old browser, a desktop with no radio:
in every one of those the picker still has to open somewhere, and opening
on ``{0, 0}`` puts a seller in the Gulf of Guinea.

So the server answers it from the one fact it has anyway — the address the
request came from. This is deliberately the *weak* signal: city-level at
best, wrong for a VPN, wrong for a mobile carrier's national NAT. It is
never a location a listing is saved with. It is the first frame of a map,
and the alternative to it is a worse first frame.

The shape mirrors the geocoder seam next door: a provider **name** through
a merge registry (:func:`registered_ip_locators`), a lazily-read settings
namespace, and no bundled keys. Two built-ins ship:

- ``maxmind`` — an OFFLINE MaxMind/GeoLite2-City database read through the
  ``geoip2`` package. No network call, no third party learning who is on
  your site, no per-request cost. The database file is the host's own
  (MaxMind requires an account to download it), which is why the path is a
  setting and there is no default.
- ``static`` — one configured point for everybody. Not a placeholder: a
  single-city marketplace genuinely has one right answer, and it beats a
  provider that is right about the country and wrong about the city.

And the floor under both: when the locator has no answer (a private
address, an unseeded database, an unconfigured point), the service falls
back to ``IP_FALLBACK_CENTER`` — or, unset, to ``MAP_DEFAULT_CENTER``, the
opening centre the map already had. The endpoint therefore always answers
200 with something a map can open on, and says in-band which of those it
is (``source``, ``precision``, ``ip_resolved``) so a frontend can tell "we
think you are in Moscow" from "we have no idea, here is the default".
"""
from .base import IpLocator, IpLocatorError
from .dto import IpLocation
from .providers import (
    BUILTIN_IP_LOCATORS,
    MaxMindIpLocator,
    StaticIpLocator,
    register_ip_locator,
    registered_ip_locators,
)
from .service import get_ip_locator, locate_ip

__all__ = [
    "IpLocation",
    "IpLocator",
    "IpLocatorError",
    "BUILTIN_IP_LOCATORS",
    "MaxMindIpLocator",
    "StaticIpLocator",
    "register_ip_locator",
    "registered_ip_locators",
    "get_ip_locator",
    "locate_ip",
]
