"""v1 URL patterns (mounted at ``/geo/api/v1/`` by ``stapel_geo.urls``).

Routes (relative to the mount):
- ``locations/`` ... location tree, search, countries, nearby, validate-uuid
- ``geocoding/`` ... geocoder proxy (search / structured / reverse / resolve)
- ``map/config`` ... basemap + picker configuration (public)
- ``ip`` ....... where the calling client appears to be (public)

The geocoder proxy is mountable on its own from
``stapel_geo.geocoding.urls`` if the location tree is not wanted.
"""
from django.urls import include, path
from stapel_core.django.api.routers import OptionalSlashRouter

from .basemap import MapConfigView
from .views import LocationViewSet

router = OptionalSlashRouter()
router.register(r"locations", LocationViewSet, basename="location")

urlpatterns = [
    path("", include(router.urls)),
    path("geocoding/", include("stapel_geo.geocoding.urls")),
    path("map/config", MapConfigView.as_view(), name="map-config"),
    path("", include("stapel_geo.ipgeo.urls")),
]
