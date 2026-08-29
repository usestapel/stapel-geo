"""IP-location URLs — mountable on their own.

The host mounts these under the geo prefix (see ``stapel_geo.urls_v1``),
or standalone when only this verb is wanted::

    path("geo/api/v1/", include("stapel_geo.ipgeo.urls"))
"""
from django.urls import path

from .views import IpLocationView

urlpatterns = [
    path("ip", IpLocationView.as_view(), name="ip-location"),
]
