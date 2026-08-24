"""The human display line for a geocoded place — shipped, not left to products.

A geocoder answers in *components*: a POI name, a street, a house number, a
district, a city, a state, a country. A human picks a location by reading
**one line**. Every product that ever wired a geocoder in re-invented the
join — badly, and differently — which is the same defect as shipping a
composer with two raw ``latitude`` / ``longitude`` fields: the library
handed over parts and called it a feature.

So every feature that leaves this module carries
``properties.formatted``: the line a picker can render as-is.

The default is deliberately conservative:

- The **house-number side of the street** follows the country, not English
  habit. ``ADDRESS_HOUSENUMBER_FIRST_COUNTRIES`` lists the alpha-2 codes
  where the number leads (``7 Tverskaya Street``); everywhere else the
  street leads (``Тверская улица, 7``, ``Hauptstraße 7``).
- A POI name is dropped when it merely repeats the street or the city, so
  ``Berlin, Berlin, Germany`` never happens.
- The postcode stays out unless ``ADDRESS_INCLUDE_POSTCODE`` asks for it —
  it is always available as a component regardless.

Swap the whole thing without forking via ``STAPEL_GEO["ADDRESS_FORMATTER"]``
(a dotted path to any ``(GeocodeProperties) -> str`` callable).
"""
from __future__ import annotations

from ..conf import geo_settings
from .dto import GeocodeProperties


def _clean(value) -> str:
    return str(value).strip() if value else ""


def _housenumber_first(countrycode: str) -> bool:
    codes = {
        str(code).upper()
        for code in (geo_settings.ADDRESS_HOUSENUMBER_FIRST_COUNTRIES or [])
    }
    return countrycode.upper() in codes


def street_line(props: GeocodeProperties) -> str:
    """``street`` + ``housenumber`` joined in the country's own order."""
    street = _clean(props.street)
    number = _clean(props.housenumber)
    if not street:
        return number
    if not number:
        return street
    if _housenumber_first(_clean(props.countrycode)):
        return f"{number} {street}"
    return f"{street}, {number}"


def format_address(props: GeocodeProperties) -> str:
    """Build the one-line human label for *props*.

    Order: place name, street + number, district (only when there is no
    street to carry it), postcode (opt-in), city, state, country. Parts
    that repeat an earlier part are dropped, so the line never stutters.
    """
    street = street_line(props)
    name = _clean(props.name)
    city = _clean(props.city) or _clean(props.county)
    district = _clean(props.district)
    state = _clean(props.state)
    country = _clean(props.country)
    postcode = _clean(props.postcode)

    parts: list[str] = []
    # The POI name earns its slot only when it says something the address
    # components do not (a venue, a landmark) — not when it IS the city.
    if name and name not in (city, state, country, _clean(props.street)):
        parts.append(name)
    if street:
        parts.append(street)
    elif district:
        parts.append(district)
    if postcode and geo_settings.ADDRESS_INCLUDE_POSTCODE:
        parts.append(postcode)
    if city:
        parts.append(city)
    if state and state != city:
        parts.append(state)
    if country:
        parts.append(country)

    seen: set[str] = set()
    unique = []
    for part in parts:
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(part)
    return ", ".join(unique)


def apply_formatter(props: GeocodeProperties) -> GeocodeProperties:
    """Stamp ``props.formatted`` using the configured formatter, in place.

    A formatter that raises must not cost the caller its geocoding result —
    a missing display line degrades a picker, an exception breaks it.
    """
    formatter = geo_settings.ADDRESS_FORMATTER
    try:
        props.formatted = formatter(props) or None
    except Exception:  # noqa: BLE001 — a label is never worth a 500
        import logging

        logging.getLogger(__name__).warning(
            "ADDRESS_FORMATTER raised; feature left without a display line",
            exc_info=True,
        )
        props.formatted = None
    return props


__all__ = ["format_address", "street_line", "apply_formatter"]
