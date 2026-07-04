"""i18n error keys of stapel-geo.

Only ``error.<status>.<slug>`` keys leave this package — human-readable
strings are translations, never literals in responses.
"""
from stapel_core.django.api.errors import register_service_errors

ERR_400_LAT_LON_REQUIRED = "error.400.lat_lon_required"
ERR_400_GEOHASH_REQUIRED = "error.400.geohash_required"
ERR_400_UUID_REQUIRED = "error.400.uuid_required"
ERR_400_INVALID_IMPORT_STATUS = "error.400.invalid_import_status"
ERR_400_INVALID_GEOJSON = "error.400.invalid_geojson"
ERR_502_GEOCODER_UNAVAILABLE = "error.502.geocoder_unavailable"

STAPEL_GEO_ERRORS = {
    ERR_400_LAT_LON_REQUIRED: "Valid latitude and longitude are required",
    ERR_400_GEOHASH_REQUIRED: "Geohash is required",
    ERR_400_UUID_REQUIRED: "Location UUID is required",
    ERR_400_INVALID_IMPORT_STATUS: "Cannot retry import with current status",
    ERR_400_INVALID_GEOJSON: "GeoJSON file is invalid",
    ERR_502_GEOCODER_UNAVAILABLE: "Geocoding provider is unavailable",
}

register_service_errors(STAPEL_GEO_ERRORS)

__all__ = [
    "STAPEL_GEO_ERRORS",
    "ERR_400_LAT_LON_REQUIRED",
    "ERR_400_GEOHASH_REQUIRED",
    "ERR_400_UUID_REQUIRED",
    "ERR_400_INVALID_IMPORT_STATUS",
    "ERR_400_INVALID_GEOJSON",
    "ERR_502_GEOCODER_UNAVAILABLE",
]
