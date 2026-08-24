"""What a point-on-map picker needs from the server, so it invents nothing.

A map component is mostly *policy*, not code: which tile server may be
called, what attribution the licence obliges you to display, how far the
user may zoom, which corner of the world the product operates in, how
long to wait before turning a keystroke into an upstream request. Every
one of those is a deployment fact. A frontend that hardcodes them ships a
different answer per product and silently breaks the licence in at least
one of them.

So the library answers them, once, from ``STAPEL_GEO``, over one
unauthenticated GET — unauthenticated because a map that cannot render
until the visitor logs in is not a map, and because the payload is
configuration the product publishes anyway (nothing here is a secret; a
tile URL that must stay private is a signed-URL problem, not a geo one).

The attribution fields are **not decoration**. OpenStreetMap data is
ODbL-licensed and the Tile Usage Policy requires visible credit; a map
that drops the line is a licence violation, not a style choice. They are
therefore mandatory fields of the payload, not optional hints, and
``requires_attribution`` says so in-band.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from stapel_core.django.api.serializers import StapelDataclassSerializer
from stapel_core.django.api.views import StapelAPIView
from stapel_core.flows import flow_step

from .conf import geo_settings
from .flows import PICK_LOCATION


@dataclass
class TileLayer:
    """The raster basemap a picker is allowed to draw.

    Attributes:
        url_template: Tile URL with {z}/{x}/{y} (and optional {s}) placeholders. Example: https://tile.openstreetmap.org/{z}/{x}/{y}.png
        subdomains: Shards for the {s} placeholder, empty when unused. Example: ["a", "b", "c"]
        attribution_html: Credit line as HTML — a licence obligation, always render one. Example: &copy; OpenStreetMap contributors
        attribution_text: Same credit as plain text (canvas, print, native). Example: © OpenStreetMap contributors
        policy_url: The tile provider's usage policy. Example: https://operations.osmfoundation.org/policies/tiles/
        requires_attribution: Whether the credit line must be visible. Example: true
        min_zoom: Lowest zoom level the layer serves. Example: 2
        max_zoom: Highest zoom level the layer serves. Example: 19
    """
    url_template: str
    attribution_html: str
    attribution_text: str
    subdomains: list[str] = field(default_factory=list)
    policy_url: Optional[str] = None
    requires_attribution: bool = True
    min_zoom: int = 2
    max_zoom: int = 19


@dataclass
class MapConfig:
    """Everything the default location picker needs before its first frame.

    Attributes:
        tiles: The basemap layer and its attribution obligations.
        default_center: Opening centre as [lat, lon], or null for "no opinion". Example: [55.7558, 37.6173]
        default_zoom: Opening zoom level. Example: 13
        picked_zoom: Zoom to settle on once a place has been chosen. Example: 17
        bbox: Operating area as [min_lon, min_lat, max_lon, max_lat], or null for worldwide. Example: [19.6, 41.2, 190.0, 81.9]
        geolocation: Whether the skin should offer the browser's position prompt. Example: true
        search_min_chars: Characters before search-as-you-type fires. Example: 3
        search_debounce_ms: Idle time before a keystroke becomes a request. Example: 350
        geohash_precision: Precision of the geohash the server stamps on a resolved point. Example: 8
        endpoints: Absolute-from-mount paths of the verbs the picker calls.
    """
    tiles: TileLayer
    default_zoom: int
    picked_zoom: int
    geolocation: bool
    search_min_chars: int
    search_debounce_ms: int
    geohash_precision: int
    endpoints: dict
    default_center: Optional[list[float]] = None
    bbox: Optional[list[float]] = None


#: Paths of the picker's own calls, relative to wherever the host mounted
#: ``stapel_geo.urls``. Shipped in the payload so the frontend has ONE
#: place to learn the surface instead of hardcoding four strings that
#: silently rot when the mount prefix changes.
ENDPOINTS = {
    "search": "api/v1/geocoding/search",
    "structured": "api/v1/geocoding/structured",
    "reverse": "api/v1/geocoding/reverse",
    "resolve": "api/v1/geocoding/resolve",
    "locations_nearby": "api/v1/locations/nearby-by-coords",
}


def build_map_config() -> MapConfig:
    """Assemble the picker's configuration from ``STAPEL_GEO`` (call time)."""
    return MapConfig(
        tiles=TileLayer(
            url_template=geo_settings.MAP_TILE_URL,
            subdomains=list(geo_settings.MAP_TILE_SUBDOMAINS or []),
            attribution_html=geo_settings.MAP_TILE_ATTRIBUTION_HTML,
            attribution_text=geo_settings.MAP_TILE_ATTRIBUTION_TEXT,
            policy_url=geo_settings.MAP_TILE_POLICY_URL,
            requires_attribution=bool(geo_settings.MAP_TILE_ATTRIBUTION_TEXT),
            min_zoom=int(geo_settings.MAP_MIN_ZOOM),
            max_zoom=int(geo_settings.MAP_MAX_ZOOM),
        ),
        default_center=(
            list(geo_settings.MAP_DEFAULT_CENTER)
            if geo_settings.MAP_DEFAULT_CENTER
            else None
        ),
        default_zoom=int(geo_settings.MAP_DEFAULT_ZOOM),
        picked_zoom=int(geo_settings.MAP_PICKED_ZOOM),
        bbox=list(geo_settings.MAP_BBOX) if geo_settings.MAP_BBOX else None,
        geolocation=bool(geo_settings.MAP_GEOLOCATION),
        search_min_chars=int(geo_settings.MAP_SEARCH_MIN_CHARS),
        search_debounce_ms=int(geo_settings.MAP_SEARCH_DEBOUNCE_MS),
        geohash_precision=int(geo_settings.GEOHASH_PRECISION),
        endpoints=dict(ENDPOINTS),
    )


class MapConfigSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = MapConfig


@extend_schema(tags=["Map"])
class MapConfigView(StapelAPIView):
    """Basemap + picker configuration. Public: a map renders before login."""

    permission_classes = [AllowAny]
    response_serializer_class = MapConfigSerializer

    @extend_schema(
        summary="Basemap and location-picker configuration",
        responses={200: MapConfigSerializer},
    )
    @flow_step(PICK_LOCATION, order=1,
               note="The picker loads its tile layer, attribution and search discipline")
    def get(self, request):
        return self.serialized_response(build_map_config())


__all__ = [
    "TileLayer",
    "MapConfig",
    "MapConfigSerializer",
    "MapConfigView",
    "build_map_config",
    "ENDPOINTS",
]
