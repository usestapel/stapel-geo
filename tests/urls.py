from django.urls import include, path

urlpatterns = [
    # Geocoder proxy at the same path the geocoding HTTP tests use in both
    # modes (mirrors tests/urls_nonspatial.py). The full spatial surface below
    # also exposes it under ``api/geocoding/`` per stapel_geo.urls.
    path("geo/geocoding/", include("stapel_geo.geocoding.urls")),
    path("geo/", include("stapel_geo.urls")),
]
