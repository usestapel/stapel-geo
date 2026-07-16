"""stapel-geo — Geographic locations and geocoding for the Stapel framework.

Public API (lazily exported, PEP 562 — importing this package never pulls
in Django or a configured settings module):

- ``geo_settings`` — resolved app settings (``stapel_geo.conf``).
- ``GeoSearchBackend`` / ``get_backend`` / ``PostgresGeoSearchBackend`` /
  ``RedisGeoSearchBackend`` — the proximity-search facade.
- ``Geocoder`` / ``GeocoderError`` / ``PhotonGeocoder`` /
  ``NominatimGeocoder`` — the geocoder seam.
- ``register_geocoder`` / ``registered_geocoders`` — the provider
  merge-registry.
- ``GeocodeResponse`` — normalized GeoJSON geocoding result.
- ``GeocodeCachePolicy`` — the geocode-cache seam.

The models (``Location``, ``GeocodeCache``) live in ``stapel_geo.models``
— import them explicitly, not from here.
"""

__all__ = [
    "GeoSearchBackend",
    "GeocodeCachePolicy",
    "GeocodeResponse",
    "Geocoder",
    "GeocoderError",
    "NominatimGeocoder",
    "PhotonGeocoder",
    "PostgresGeoSearchBackend",
    "RedisGeoSearchBackend",
    "geo_settings",
    "get_backend",
    "register_geocoder",
    "registered_geocoders",
]

# name -> submodule that defines it. Resolution is deferred until first
# attribute access so that `import stapel_geo` stays Django-free.
_LAZY_EXPORTS = {
    "geo_settings": ".conf",
    "GeoSearchBackend": ".search.base",
    "get_backend": ".search",
    "PostgresGeoSearchBackend": ".search.postgres",
    "RedisGeoSearchBackend": ".search.redis",
    "Geocoder": ".geocoding.base",
    "GeocoderError": ".geocoding.base",
    "PhotonGeocoder": ".geocoding.providers",
    "NominatimGeocoder": ".geocoding.providers",
    "register_geocoder": ".geocoding.providers",
    "registered_geocoders": ".geocoding.providers",
    "GeocodeResponse": ".geocoding.dto",
    "GeocodeCachePolicy": ".geocoding.cache",
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
