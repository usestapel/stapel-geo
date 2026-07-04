from django.urls import include, path

urlpatterns = [
    path("geo/", include("stapel_geo.urls")),
]
