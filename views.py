"""DRF views for the stapel-geo location API (flat, GDAL-free).

Location listing/search/countries/children, proximity search through the
search facade, and UUID validation. Thin views over the ORM and the
``services`` layer; errors use the StapelError envelope.
"""
from __future__ import annotations

import math

from django.core.exceptions import ValidationError
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from stapel_core.django.api.errors import StapelErrorResponse, StapelResponse
from stapel_core.django.api.permissions import ReadOnlyOrSuperUser
from stapel_core.flows import flow_step

from . import services
from .conf import geo_settings
from .dto import ValidateUuidResponse
from .errors import (
    ERR_400_GEOHASH_REQUIRED,
    ERR_400_INVALID_PARAMS,
    ERR_400_LAT_LON_REQUIRED,
    ERR_400_UUID_REQUIRED,
)
from .flows import LOCATION_BROWSE, LOCATION_NEARBY, LOCATION_RESOLVE
from .models import Location
from .serializers import (
    LocationCompactSerializer,
    LocationSerializer,
    ValidateUuidResponseSerializer,
)


@extend_schema(tags=["Locations"])
class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [ReadOnlyOrSuperUser]

    def get_serializer_class(self):
        if self.action == "list":
            return LocationCompactSerializer
        return LocationSerializer

    @extend_schema(
        summary="List and search locations",
        parameters=[
            OpenApiParameter("search", OpenApiTypes.STR, required=False,
                             description="Search query (min 2 chars) on location name."),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False,
                             description="Max results (default 10, max 50)."),
        ],
    )
    @flow_step(LOCATION_BROWSE, order=1,
               note="List root locations or search the tree by name")
    def list(self, request, *args, **kwargs):
        search = request.query_params.get("search", "").strip()
        if len(search) < 2:
            queryset = self.get_queryset().filter(tn_parent__isnull=True).order_by("name")
            return StapelResponse(LocationCompactSerializer(queryset, many=True))
        limit = self._parse_limit(request)
        if limit is None:
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        queryset = self.get_queryset().filter(name__icontains=search).order_by("name")[:limit]
        return StapelResponse(LocationCompactSerializer(queryset, many=True))

    def get_object(self):
        """Resolve a Location by integer id or by cross-service UUID.

        A ``pk`` that is neither a known id nor a valid UUID is a miss (404),
        not a 500 — Django raises ``ValidationError`` when a malformed UUID
        reaches the query, so that is caught and treated as "not found".
        """
        pk = self.kwargs.get("pk")
        queryset = self.get_queryset()
        if pk.isdigit():
            obj = queryset.filter(pk=int(pk)).first()
            if obj:
                return obj
        try:
            obj = queryset.filter(uuid=pk).first()
        except (ValidationError, ValueError):
            obj = None
        if obj:
            return obj
        from django.http import Http404
        raise Http404("Location not found")

    @extend_schema(summary="Countries (root locations)",
                   responses={200: LocationCompactSerializer(many=True)})
    @flow_step(LOCATION_BROWSE, order=2, note="Fetch the root level (countries)")
    @action(detail=False, methods=["get"], url_path="countries")
    def countries(self, request):
        queryset = self.get_queryset().filter(tn_parent__isnull=True).order_by("name")
        return StapelResponse(LocationCompactSerializer(queryset, many=True))

    @extend_schema(summary="Children of a location",
                   responses={200: LocationCompactSerializer(many=True)})
    @flow_step(LOCATION_BROWSE, order=3, note="Drill into a node's children")
    @action(detail=False, methods=["get"], url_path=r"by-parent/(?P<parent_id>\d+)")
    def by_parent(self, request, parent_id=None):
        queryset = self.get_queryset().filter(tn_parent_id=parent_id).order_by("name")
        return StapelResponse(LocationCompactSerializer(queryset, many=True))

    @extend_schema(responses={200: ValidateUuidResponseSerializer})
    @flow_step(LOCATION_RESOLVE, order=1,
               note="Check a location UUID exists (malformed = valid: false)")
    @action(detail=False, methods=["get"], url_path=r"validate-uuid/(?P<uuid>[^/.]+)")
    def validate_uuid(self, request, uuid=None):
        if not uuid:
            return StapelErrorResponse(400, ERR_400_UUID_REQUIRED)
        try:
            exists = self.get_queryset().filter(uuid=uuid).exists()
        except (ValidationError, ValueError):
            # A malformed UUID is simply not valid — not a server error.
            exists = False
        dto = ValidateUuidResponse(valid=exists, uuid=uuid)
        return StapelResponse(ValidateUuidResponseSerializer(dto))

    @extend_schema(
        summary="Find nearby locations by coordinates",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("lon", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("precision", OpenApiTypes.INT, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: LocationCompactSerializer(many=True)},
    )
    @flow_step(LOCATION_NEARBY, order=1,
               note="Nearest locations to a coordinate (top-K, exact haversine)")
    @action(detail=False, methods=["get"], url_path="nearby-by-coords")
    def nearby_by_coords(self, request):
        try:
            lat = float(request.query_params.get("lat"))
            lon = float(request.query_params.get("lon"))
        except (TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_LAT_LON_REQUIRED)
        # Reject NaN/inf and out-of-range coordinates — pygeohash.encode would
        # otherwise raise on them (a 500 on user input).
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return StapelErrorResponse(400, ERR_400_LAT_LON_REQUIRED)
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return StapelErrorResponse(400, ERR_400_LAT_LON_REQUIRED)
        try:
            precision = int(request.query_params.get("precision", geo_settings.NEARBY_PRECISION))
        except (TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        precision = max(1, min(12, precision))
        limit = self._parse_limit(request)
        if limit is None:
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        rows = services.nearby_rows_by_coords(lat, lon, precision, limit)
        return StapelResponse(LocationCompactSerializer(rows, many=True))

    @extend_schema(
        summary="Find nearby locations by geohash",
        parameters=[
            OpenApiParameter("geohash", OpenApiTypes.STR, required=True),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
        ],
        responses={200: LocationCompactSerializer(many=True)},
    )
    @flow_step(LOCATION_NEARBY, order=2,
               note="Nearest locations to a geohash (decoded to its cell centre)")
    @action(detail=False, methods=["get"], url_path="nearby-by-geohash")
    def nearby_by_geohash(self, request):
        gh = request.query_params.get("geohash")
        if not gh:
            return StapelErrorResponse(400, ERR_400_GEOHASH_REQUIRED)
        limit = self._parse_limit(request)
        if limit is None:
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        try:
            rows = services.nearby_rows_by_geohash(gh, limit)
        except ValueError:
            # pygeohash rejects non-geohash characters — user input, not a 500.
            return StapelErrorResponse(400, ERR_400_GEOHASH_REQUIRED)
        return StapelResponse(LocationCompactSerializer(rows, many=True))

    def _parse_limit(self, request):
        """Coerce and clamp ``limit``; ``None`` signals an invalid value."""
        try:
            limit = int(request.query_params.get("limit", geo_settings.NEARBY_LIMIT))
        except (TypeError, ValueError):
            return None
        return max(1, min(limit, geo_settings.NEARBY_MAX_LIMIT))


__all__ = ["LocationViewSet"]
