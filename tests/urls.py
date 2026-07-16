"""Test URLconf — the canonical host mount (``/geo/`` -> ``api/v1/...``)."""
from django.urls import include, path

urlpatterns = [
    path("geo/", include("stapel_geo.urls")),
]
