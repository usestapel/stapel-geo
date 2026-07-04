"""Non-spatial test URLconf — only the GDAL-free geocoder proxy is mounted."""
from django.urls import include, path

urlpatterns = [
    path("geo/geocoding/", include("stapel_geo.geocoding.urls")),
]
