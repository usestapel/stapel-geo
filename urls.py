"""URL patterns — no global prefix here, the host project mounts them:

    path("geo/", include("stapel_geo.urls"))

Routes (relative to the mount):
- ``api/locations/`` ... location tree, search, countries, nearby, validate-uuid
- ``api/geofiles/``  ... GADM GeoFile import management
- ``api/geocoding/`` ... geocoder proxy (search / structured / reverse)

Importing this module pulls in the spatial views (GDAL). The geocoder
proxy is GDAL-free and can be mounted on its own from
``stapel_geo.geocoding.urls`` if the location tree is not wanted.
"""
from django.urls import include, path
from stapel_core.django.api.routers import OptionalSlashRouter

from .views import GeoFileViewSet, LocationViewSet

router = OptionalSlashRouter()
router.register(r"locations", LocationViewSet, basename="location")
router.register(r"geofiles", GeoFileViewSet, basename="geofile")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/geocoding/", include("stapel_geo.geocoding.urls")),
]
