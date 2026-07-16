"""v1 URL patterns (mounted at ``/geo/api/v1/`` by ``stapel_geo.urls``).

Routes (relative to the mount):
- ``locations/`` ... location tree, search, countries, nearby, validate-uuid
- ``geocoding/`` ... geocoder proxy (search / structured / reverse)

The geocoder proxy is mountable on its own from
``stapel_geo.geocoding.urls`` if the location tree is not wanted.
"""
from django.urls import include, path
from stapel_core.django.api.routers import OptionalSlashRouter

from .views import LocationViewSet

router = OptionalSlashRouter()
router.register(r"locations", LocationViewSet, basename="location")

urlpatterns = [
    path("", include(router.urls)),
    path("geocoding/", include("stapel_geo.geocoding.urls")),
]
