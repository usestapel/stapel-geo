"""stapel-geo — Geographic locations and geocoding for the Stapel framework.

Public API (lazily exported, PEP 562 — importing this package never pulls
in Django, GDAL, or a configured settings module):

- ``geo_settings`` — resolved app settings (``stapel_geo.conf``).
- ``Geocoder`` / ``PhotonGeocoder`` / ``GeocoderError`` — the geocoder seam.
- ``GeocodeResponse`` — normalized GeoJSON geocoding result.
- ``ImportStatus`` / ``GeoFileImporter`` — the GDAL-free GADM import machine.

The spatial models (``Location``, ``GeoFile``) live in ``stapel_geo.models``
and require GDAL + a spatial DB — import them explicitly, not from here.
"""

__all__ = [
    "GeocodeResponse",
    "Geocoder",
    "GeocoderError",
    "GeoFileImporter",
    "ImportStatus",
    "PhotonGeocoder",
    "geo_settings",
]

# name -> submodule that defines it. Resolution is deferred until first
# attribute access so that `import stapel_geo` stays Django-free / GDAL-free.
_LAZY_EXPORTS = {
    "geo_settings": ".conf",
    "Geocoder": ".geocoding.base",
    "GeocoderError": ".geocoding.base",
    "PhotonGeocoder": ".geocoding.providers",
    "GeocodeResponse": ".geocoding.dto",
    "ImportStatus": ".imports",
    "GeoFileImporter": ".imports",
}


def __getattr__(name):
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        value = getattr(import_module(_LAZY_EXPORTS[name], __name__), name)
        globals()[name] = value  # cache for subsequent lookups
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
