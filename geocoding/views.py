"""Geocoder proxy views — JWT-guarded, throttled, provider-agnostic.

Each view goes through ``service.geocode()``: provider resolution by
**name** (the ``GEOCODER``/``GEOCODERS`` merge-registry), cache lookup
(``GEOCODE_CACHE_POLICY``), and a GeocodeCache ledger row per call.
PAYG discipline: a ``ScopedRateThrottle`` (scope ``"geocoding"``, rate
``STAPEL_GEO["GEOCODER_THROTTLE"]``) caps how fast any caller can burn a
metered upstream key. These views never mention a provider by name.
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from stapel_core.core.language import parse_accept_language
from stapel_core.django.api.errors import StapelErrorResponse, StapelResponse
from stapel_core.django.api.permissions import IsNotAnonymousUser
from stapel_core.flows import flow_step

from ..errors import ERR_400_LAT_LON_REQUIRED, ERR_502_GEOCODER_UNAVAILABLE
from ..flows import GEOCODE_ADDRESS
from ..seams import SerializerSeamMixin
from .base import GeocoderError
from .serializers import GeocodeResponseSerializer
from .service import geocode

# Query params the proxy consumes itself, plus the names of the provider
# methods' own parameters. Both are excluded from the forwarded extras: the
# former because the proxy handles them, the latter because forwarding e.g.
# ``?query=…`` or ``?self=…`` as a kwarg collides with a positional argument
# and raises TypeError ("multiple values for argument") — a 500 on user
# input. Everything else is passed through to the provider as extras.
_PROXY_CONSUMED = {"q", "lat", "lon", "lang", "limit"}
_METHOD_PARAMS = {"self", "query", "lat", "lng", "lon", "lang", "limit", "params", "verb"}
_RESERVED = _PROXY_CONSUMED | _METHOD_PARAMS

# Upper bound for a forwarded ``limit`` so a user's oversized value cannot
# provoke an upstream 4xx that would then be masked as a 502 "unavailable".
_MAX_LIMIT = 50


class GeocodingThrottle(ScopedRateThrottle):
    """ScopedRateThrottle whose rate comes from ``STAPEL_GEO`` (lazily).

    DRF resolves scoped rates from the global ``DEFAULT_THROTTLE_RATES``
    setting; a library module cannot own that dict, so the rate is read
    from the module namespace instead (``GEOCODER_THROTTLE``).
    """

    scope = "geocoding"

    def get_rate(self):
        from ..conf import geo_settings

        return geo_settings.GEOCODER_THROTTLE


def _resolve_lang(request):
    lang = request.query_params.get("lang")
    if lang:
        return lang
    return parse_accept_language(request.META.get("HTTP_ACCEPT_LANGUAGE", ""))


def _resolve_limit(request):
    """Coerce and clamp the requested ``limit``; ``None`` on absent/invalid."""
    raw = request.query_params.get("limit")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(1, min(value, _MAX_LIMIT))


def _extra_params(request):
    return {
        key: value
        for key, value in request.query_params.items()
        if key not in _RESERVED
    }


def _respond(view, response):
    serializer = view.get_response_serializer_class()(response)
    return StapelResponse(serializer)


class _GeocodeView(SerializerSeamMixin, APIView):
    permission_classes = [IsNotAnonymousUser]
    throttle_classes = [GeocodingThrottle]
    throttle_scope = "geocoding"
    response_serializer_class = GeocodeResponseSerializer


@extend_schema(tags=["Geocoding"])
class GeocodeSearchView(_GeocodeView):
    """Forward geocoding — search places by free-text query."""

    @extend_schema(
        summary="Search places by text",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, required=True, description="Search query"),
            OpenApiParameter("lang", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: GeocodeResponseSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=1,
               note="Free-text forward geocoding (throttled, cached, ledgered)")
    def get(self, request):
        query = request.query_params.get("q", "")
        limit = _resolve_limit(request)
        try:
            response = geocode(
                "search",
                query=query,
                lang=_resolve_lang(request),
                limit=limit,
                **_extra_params(request),
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return _respond(self, response)


@extend_schema(tags=["Geocoding"])
class GeocodeReverseView(_GeocodeView):
    """Reverse geocoding — coordinates to address."""

    @extend_schema(
        summary="Reverse geocode coordinates",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("lon", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("lang", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: GeocodeResponseSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=3,
               note="Map pin to address (reverse geocoding)")
    def get(self, request):
        try:
            lat = float(request.query_params["lat"])
            lng = float(request.query_params["lon"])
        except (KeyError, TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_LAT_LON_REQUIRED)
        limit = _resolve_limit(request)
        try:
            response = geocode(
                "reverse",
                lat=lat,
                lng=lng,
                lang=_resolve_lang(request),
                limit=limit,
                **_extra_params(request),
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return _respond(self, response)


@extend_schema(tags=["Geocoding"])
class GeocodeStructuredView(_GeocodeView):
    """Structured address search — search by address components."""

    @extend_schema(
        summary="Structured address search",
        parameters=[
            OpenApiParameter("city", OpenApiTypes.STR, required=False),
            OpenApiParameter("street", OpenApiTypes.STR, required=False),
            OpenApiParameter("postcode", OpenApiTypes.STR, required=False),
            OpenApiParameter("countrycode", OpenApiTypes.STR, required=False),
            OpenApiParameter("lang", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: GeocodeResponseSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=2,
               note="Search by address components (city, street, postcode, ...)")
    def get(self, request):
        limit = _resolve_limit(request)
        try:
            response = geocode(
                "structured",
                lang=_resolve_lang(request),
                limit=limit,
                **_extra_params(request),
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return _respond(self, response)


__all__ = [
    "GeocodingThrottle",
    "GeocodeSearchView",
    "GeocodeReverseView",
    "GeocodeStructuredView",
]
