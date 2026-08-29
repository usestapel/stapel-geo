"""``GET geo/api/v1/ip`` — where to open the map for THIS visitor.

Public by default, because the whole point is to answer before anyone has
an account, and throttled by the same PAYG reflex as the geocoder proxy:
the endpoint is cheap on an offline database and is not cheap on a metered
upstream a host may swap in, so the brake ships with the library.

Two properties of the answer are worth stating in one place, because a
frontend depends on both:

- **It always answers.** An unknown address, a broken database, a locator
  a deployment never configured — every one of those comes back 200 with
  the fallback centre and ``ip_resolved: false``. A map that cannot open
  is a worse outcome than a map that opens in the wrong city, and a
  frontend that has to branch on 4xx here would just hardcode a centre.
- **It says how much it knows.** ``source`` / ``precision`` /
  ``ip_resolved`` are the difference between "we think you are in Moscow"
  and "we have no idea, here is where this site lives". A UI that shows
  the first as if it were a confirmed address is lying to its user.

The one case that is NOT 200 is a deployment with no locator answer and no
fallback centre at all — an explicit refusal to have an opinion, answered
204 so a caller can tell it from a centre it should use.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from stapel_core.django.api.views import StapelAPIView
from stapel_core.flows import flow_step

from ..flows import PICK_LOCATION
from .serializers import IpLocationSerializer
from .service import locate_ip


class IpGeoThrottle(ScopedRateThrottle):
    """Scoped throttle whose rate comes from ``STAPEL_GEO`` (lazily).

    Same shape as the geocoder's: a library cannot own DRF's global
    ``DEFAULT_THROTTLE_RATES``, so the rate is read from the namespace.
    Anonymous callers get ``IP_ANON_THROTTLE`` — and unlike the geocoder,
    anonymous is the EXPECTED caller here, so that rate is the live one.
    """

    scope = "geo_ip"

    def allow_request(self, request, view):
        self._request = request
        return super().allow_request(request, view)

    def get_rate(self):
        from ..conf import geo_settings

        user = getattr(getattr(self, "_request", None), "user", None)
        if user is not None and not user.is_authenticated:
            anon_rate = geo_settings.IP_ANON_THROTTLE
            if anon_rate:
                return anon_rate
        return geo_settings.IP_THROTTLE


@extend_schema(tags=["Map"])
class IpLocationView(StapelAPIView):
    """Place the calling client by its own IP address."""

    throttle_classes = [IpGeoThrottle]
    throttle_scope = "geo_ip"
    response_serializer_class = IpLocationSerializer

    #: ``None`` means "ask the settings"; a list pins the view.
    permission_classes = None

    def get_permissions(self):
        if self.permission_classes is not None:
            return super().get_permissions()
        from django.utils.module_loading import import_string

        from ..conf import geo_settings

        return [
            import_string(dotted_path)()
            for dotted_path in (geo_settings.IP_PERMISSIONS or [])
        ]

    @extend_schema(
        summary="Where the calling client appears to be",
        description=(
            "A coarse, city-at-best guess derived from the caller's own IP "
            "address, for opening a map before the browser's geolocation "
            "prompt has been answered — or after it was refused. Never a "
            "location to store on a record. Answers 200 with the "
            "deployment's fallback centre (`ip_resolved: false`) when the "
            "address cannot be placed, and 204 when the deployment has "
            "configured no fallback centre either."
        ),
        responses={200: IpLocationSerializer, 204: None},
    )
    @flow_step(PICK_LOCATION, order=2,
               note="The visitor is placed from their own address, so the map "
                    "opens somewhere real before anyone is asked for anything")
    def get(self, request):
        from django.utils.module_loading import import_string

        from ..conf import geo_settings

        resolver = geo_settings.IP_CLIENT_IP_RESOLVER
        if isinstance(resolver, str):
            resolver = import_string(resolver)
        location = locate_ip(resolver(request))
        if location is None:
            return Response(status=204)
        return self.serialized_response(location)


__all__ = ["IpGeoThrottle", "IpLocationView"]
