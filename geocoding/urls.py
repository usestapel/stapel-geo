"""Geocoder proxy URLs — GDAL-free, mountable on their own.

The host mounts these under the geo prefix (see ``stapel_geo.urls``), or
standalone when only the geocoder proxy is wanted::

    path("geo/geocoding/", include("stapel_geo.geocoding.urls"))
"""
from django.urls import path

from .views import GeocodeReverseView, GeocodeSearchView, GeocodeStructuredView

urlpatterns = [
    path("search", GeocodeSearchView.as_view(), name="geocode-search"),
    path("structured", GeocodeStructuredView.as_view(), name="geocode-structured"),
    path("reverse", GeocodeReverseView.as_view(), name="geocode-reverse"),
]
