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
- ``stapel_geo.W005`` — ``PHOTON_LANGUAGE_FALLBACK`` is not one of
  ``PHOTON_LANGUAGES``, so the clamp lands on a value Photon rejects.
- ``stapel_geo.W006`` — the site's own ``LANGUAGE_CODE`` is not in
  ``PHOTON_LANGUAGES``: place names will come back in the fallback
  language, not the site's. This is the check that would have caught the
  "Russian product, English addresses" defect on the first deploy.
- ``stapel_geo.W007`` — the OSM Foundation's public tile server is
  configured as the basemap outside DEBUG. Its Tile Usage Policy
  forbids that; a product needs its own tiles.
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


#: Substring identifying the OSM Foundation's own tile server, whose Tile
#: Usage Policy forbids production/commercial use (W007).
_PUBLIC_OSM_TILES = "tile.openstreetmap.org"


@checks.register("stapel_geo")
def check_geocoder_languages(app_configs, **kwargs):
    """Catch the "asked for Russian, got English" class of defect at deploy.

    ``PHOTON_LANGUAGES`` is a statement of fact about the Lucene index on
    disk, not a preference: the prebuilt GraphHopper dumps carry
    ``default, en, de, fr`` and Photon answers HTTP 400 for anything else
    rather than degrading. The provider therefore clamps — and a clamp
    nobody is told about is exactly how a Russian marketplace ends up
    serving English street names with no error anywhere.

    Two ways that goes wrong, one warning each: a fallback the index does
    not have (W005), and a *site language* the index does not have
    (W006). Both are W-level: the geocoder still answers, it just answers
    in the wrong language, and blocking a deploy over it would be worse
    than the defect.
    """
    from django.conf import settings

    from .conf import geo_settings

    if geo_settings.GEOCODER != "photon":
        return []

    languages = [str(code) for code in (geo_settings.PHOTON_LANGUAGES or [])]
    supported = set(languages)
    issues = []

    fallback = geo_settings.PHOTON_LANGUAGE_FALLBACK
    if fallback and fallback not in supported:
        issues.append(
            checks.Warning(
                f"STAPEL_GEO['PHOTON_LANGUAGE_FALLBACK'] is {fallback!r}, which is "
                f"not in PHOTON_LANGUAGES ({languages}). Every request for an "
                "unsupported language will clamp to a value Photon rejects with "
                "HTTP 400, and the caller will see 502 geocoder_unavailable.",
                hint="Use 'default' (Photon's local-name mode, the shipped "
                     "default), or list the fallback in PHOTON_LANGUAGES.",
                id="stapel_geo.W005",
            )
        )

    site_language = str(getattr(settings, "LANGUAGE_CODE", "") or "")
    base = site_language.replace("_", "-").split("-")[0].lower()
    if base and base not in supported and site_language not in supported:
        issues.append(
            checks.Warning(
                f"LANGUAGE_CODE is {site_language!r} but STAPEL_GEO"
                f"['PHOTON_LANGUAGES'] is {languages}: the Photon index does not "
                f"carry {base!r}, so geocoded place names will come back as "
                f"{geo_settings.PHOTON_LANGUAGE_FALLBACK!r}, not in the site's "
                "language.",
                hint=(
                    f"If {geo_settings.PHOTON_LANGUAGE_FALLBACK!r} is 'default' "
                    "this is usually FINE — Photon's 'default' is the local name "
                    "on the map, which in a single-country product is already the "
                    f"right language. To index {base!r} for real, build the "
                    "database from the JSON dump instead of the prebuilt one: "
                    f"`java -jar photon.jar import -languages {base},en ...`, then "
                    f"add {base!r} to STAPEL_GEO['PHOTON_LANGUAGES']. Listing it "
                    "WITHOUT rebuilding the index makes every request 502."
                ),
                id="stapel_geo.W006",
            )
        )
    return issues


@checks.register("stapel_geo")
def check_basemap(app_configs, **kwargs):
    """The default tile server is a development default, and says so.

    ``tile.openstreetmap.org`` is donated infrastructure: its Tile Usage
    Policy rules out heavy and commercial use, which every product this
    library is for. Same stance as the public Nominatim provider — ship
    something that works on a laptop, refuse to let it reach production
    unnoticed.
    """
    from django.conf import settings

    from .conf import geo_settings

    if getattr(settings, "DEBUG", False):
        return []
    if _PUBLIC_OSM_TILES not in str(geo_settings.MAP_TILE_URL or ""):
        return []
    return [
        checks.Warning(
            "STAPEL_GEO['MAP_TILE_URL'] points at the OpenStreetMap Foundation's "
            "public tile server, whose Tile Usage Policy forbids heavy or "
            "commercial use. It is the library's development default.",
            hint="Point MAP_TILE_URL at your own tile server or a paid provider "
                 f"before serving real traffic ({geo_settings.MAP_TILE_POLICY_URL}). "
                 "Keep an attribution line either way — it is a licence "
                 "obligation, not a style choice.",
            id="stapel_geo.W007",
        )
    ]


__all__ = [
    "check_geocoder",
    "check_search_backend",
    "check_geocoder_languages",
    "check_basemap",
]
