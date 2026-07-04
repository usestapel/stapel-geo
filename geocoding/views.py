"""Geocoder proxy views — JWT-guarded, provider-agnostic (GDAL-free).

Each view resolves the configured provider through the ``GEOCODER`` seam,
resolves the result language from the request, and returns a normalized
GeoJSON FeatureCollection. Providers are swappable via
``STAPEL_GEO["GEOCODER"]`` — these views never mention Photon by name.
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.views import APIView
from stapel_core.core.language import parse_accept_language
from stapel_core.django.api.errors import StapelErrorResponse, StapelResponse
from stapel_core.django.api.permissions import IsNotAnonymousUser

from ..errors import ERR_400_LAT_LON_REQUIRED, ERR_502_GEOCODER_UNAVAILABLE
from ..seams import SerializerSeamMixin
from .base import GeocoderError
from .serializers import GeocodeResponseSerializer
from .service import get_geocoder

# Query params that the proxy consumes itself; everything else is forwarded
# to the provider as provider-specific extras.
_RESERVED = {"q", "lat", "lon", "lang", "limit"}


def _resolve_lang(request):
    lang = request.query_params.get("lang")
    if lang:
        return lang
    return parse_accept_language(request.META.get("HTTP_ACCEPT_LANGUAGE", ""))


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
    def get(self, request):
        query = request.query_params.get("q", "")
        limit = request.query_params.get("limit")
        try:
            response = get_geocoder().search(
                query, lang=_resolve_lang(request), limit=limit, **_extra_params(request)
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
    def get(self, request):
        try:
            lat = float(request.query_params["lat"])
            lng = float(request.query_params["lon"])
        except (KeyError, TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_LAT_LON_REQUIRED)
        limit = request.query_params.get("limit")
        try:
            response = get_geocoder().reverse(
                lat, lng, lang=_resolve_lang(request), limit=limit, **_extra_params(request)
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
    def get(self, request):
        limit = request.query_params.get("limit")
        try:
            response = get_geocoder().structured(
                lang=_resolve_lang(request), limit=limit, **_extra_params(request)
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return _respond(self, response)


__all__ = ["GeocodeSearchView", "GeocodeReverseView", "GeocodeStructuredView"]
