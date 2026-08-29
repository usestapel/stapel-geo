"""What an IP address is worth as a location, said honestly.

The payload carries the point a map opens on AND how much to trust it.
Both halves matter: a frontend that cannot distinguish "your city" from
"the site's default" either lies to the user ("we found you!") or refuses
to use a perfectly good first frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Ordered from most to least specific. ``default`` means the locator had
#: nothing and the configured fallback centre answered instead.
PRECISIONS = ("city", "region", "country", "default")


@dataclass
class IpLocation:
    """A guess at where the caller is, with its provenance attached.

    Attributes:
        lat: Latitude of the point a map should open on. Example: 55.7558
        lon: Longitude of the point a map should open on. Example: 37.6173
        source: Which locator answered — a provider name, or "fallback". Example: maxmind
        precision: How specific the answer is: city, region, country or default. Example: city
        ip_resolved: Whether this came from the caller's address at all. Example: true
        label: One human line for the place, or null when there is none to show. Example: Moscow, Russia
        city: City name when the locator knows one. Example: Moscow
        region: First-level subdivision when the locator knows one. Example: Moscow
        country: Country name when the locator knows one. Example: Russia
        country_code: ISO-3166-1 alpha-2 country code. Example: RU
        accuracy_radius_km: Radius the provider itself claims, when it claims one. Example: 20
    """

    lat: float
    lon: float
    source: str
    precision: str = "default"
    ip_resolved: bool = False
    label: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    accuracy_radius_km: Optional[float] = None


def build_label(*parts: Optional[str]) -> Optional[str]:
    """Join the non-empty *parts* into one display line, de-duplicated.

    ``("Moscow", "Moscow", "Russia")`` — a city whose region carries the
    same name, which is common — must read "Moscow, Russia" and not
    "Moscow, Moscow, Russia".
    """
    seen: list[str] = []
    for part in parts:
        value = (part or "").strip()
        if value and value not in seen:
            seen.append(value)
    return ", ".join(seen) or None


__all__ = ["IpLocation", "PRECISIONS", "build_label"]
