"""Geocoder proxy views — provider-agnostic, configurable-guard, throttled.

Each view goes through ``service.geocode()`` / ``service.resolve_point()``:
provider resolution by **name** (the ``GEOCODER``/``GEOCODERS`` merge-
registry), cache lookup (``GEOCODE_CACHE_POLICY``), and a GeocodeCache
ledger row per call. PAYG discipline: a ``ScopedRateThrottle`` (scope
``"geocoding"``, rate ``STAPEL_GEO["GEOCODER_THROTTLE"]``, or
``GEOCODER_ANON_THROTTLE`` for a caller with no identity) caps how fast
anyone can burn a metered upstream key. These views never mention a
provider by name.

The four verbs, and who they are for:

- ``search`` — the search-as-you-type field on a location picker. Accepts
  the map's own viewport (``bias_lat``/``bias_lon``) and the product's
  operating area (``bbox``), because a picker that offers a street in
  Ohio to someone panning around Moscow is not a picker.
- ``structured`` — the same by components, when the caller already has
  city/street/postcode split.
- ``reverse`` — coordinates to place(s), the raw GeoJSON form.
- ``resolve`` — coordinates to ONE confirmable place, the form a UI can
  render directly: display line, components, geohash, alternatives.
  "Detect my position" is one call to this, not three to the others.
"""
from __future__ import annotations

import math

from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.throttling import ScopedRateThrottle
from stapel_core.core.language import parse_accept_language
from stapel_core.django.api.errors import StapelErrorResponse
from stapel_core.django.api.views import StapelAPIView
from stapel_core.flows import flow_step

from ..errors import (
    ERR_400_INVALID_BBOX,
    ERR_400_INVALID_PARAMS,
    ERR_400_LAT_LON_REQUIRED,
    ERR_502_GEOCODER_UNAVAILABLE,
)
from ..flows import GEOCODE_ADDRESS, PICK_LOCATION
from .base import GeocoderError
from .serializers import GeocodeResponseSerializer, PlaceResolutionSerializer
from .service import geocode, resolve_point

# Query params the proxy consumes itself, plus the names of the provider
# methods' own parameters. Both are excluded from the forwarded extras: the
# former because the proxy handles them, the latter because forwarding e.g.
# ``?query=…`` or ``?self=…`` as a kwarg collides with a positional argument
# and raises TypeError ("multiple values for argument") — a 500 on user
# input. Everything else is passed through to the provider as extras.
_PROXY_CONSUMED = {
    "q", "lat", "lon", "lang", "limit", "bbox", "bias_lat", "bias_lon",
    "bias_scale", "zoom", "nearest", "radius_km",
}
_METHOD_PARAMS = {
    "self", "query", "lat", "lng", "lon", "lang", "limit", "params", "verb",
    "bbox", "bias_lat", "bias_lon", "bias_scale", "zoom", "nearest", "radius_km",
}
_RESERVED = _PROXY_CONSUMED | _METHOD_PARAMS

# Upper bound for a forwarded ``limit`` so a user's oversized value cannot
# provoke an upstream 4xx that would then be masked as a 502 "unavailable".
_MAX_LIMIT = 50


class GeocodingThrottle(ScopedRateThrottle):
    """ScopedRateThrottle whose rate comes from ``STAPEL_GEO`` (lazily).

    DRF resolves scoped rates from the global ``DEFAULT_THROTTLE_RATES``
    setting; a library module cannot own that dict, so the rate is read
    from the module namespace instead (``GEOCODER_THROTTLE``).

    A caller with no identity gets ``GEOCODER_ANON_THROTTLE`` instead.
    That rate is dormant under the default permission (anonymous callers
    are refused outright) and becomes the only brake the moment a product
    opens ``GEOCODER_PERMISSIONS`` for a public search page — which it
    will, so the brake ships with the library rather than being
    remembered later.
    """

    scope = "geocoding"

    def allow_request(self, request, view):
        self._request = request
        return super().allow_request(request, view)

    def get_rate(self):
        from ..conf import geo_settings

        user = getattr(getattr(self, "_request", None), "user", None)
        if user is not None and not user.is_authenticated:
            anon_rate = geo_settings.GEOCODER_ANON_THROTTLE
            if anon_rate:
                return anon_rate
        return geo_settings.GEOCODER_THROTTLE


class _InvalidParam(Exception):
    """A query parameter the caller got wrong (surfaces as 400, never 500)."""

    def __init__(self, error_key: str):
        super().__init__(error_key)
        self.error_key = error_key


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


def _require_coordinate(lat, lon):
    """Reject NaN/inf and out-of-range pairs before they reach the provider."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise _InvalidParam(ERR_400_LAT_LON_REQUIRED)
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise _InvalidParam(ERR_400_LAT_LON_REQUIRED)


def _required_coordinate(request):
    """``lat``/``lon`` from the query string, validated."""
    try:
        lat = float(request.query_params["lat"])
        lon = float(request.query_params["lon"])
    except (KeyError, TypeError, ValueError):
        raise _InvalidParam(ERR_400_LAT_LON_REQUIRED) from None
    _require_coordinate(lat, lon)
    return lat, lon


def _resolve_bbox(request):
    """Parse ``?bbox=min_lon,min_lat,max_lon,max_lat``, or fall back to settings.

    An absent parameter inherits ``STAPEL_GEO["MAP_BBOX"]`` — the product's
    operating area is a deployment fact, not something every caller has to
    remember to send. An explicit, malformed one is a 400: silently
    ignoring it would widen a search the caller believed it had narrowed.
    """
    from ..conf import geo_settings

    raw = request.query_params.get("bbox")
    if raw is None or raw == "":
        return geo_settings.MAP_BBOX
    parts = [piece.strip() for piece in str(raw).split(",")]
    if len(parts) != 4:
        raise _InvalidParam(ERR_400_INVALID_BBOX)
    try:
        min_lon, min_lat, max_lon, max_lat = (float(piece) for piece in parts)
    except (TypeError, ValueError):
        raise _InvalidParam(ERR_400_INVALID_BBOX) from None
    for value in (min_lat, max_lat):
        if not math.isfinite(value) or not -90 <= value <= 90:
            raise _InvalidParam(ERR_400_INVALID_BBOX)
    for value in (min_lon, max_lon):
        if not math.isfinite(value) or not -180 <= value <= 180:
            raise _InvalidParam(ERR_400_INVALID_BBOX)
    if min_lat > max_lat:
        raise _InvalidParam(ERR_400_INVALID_BBOX)
    # min_lon > max_lon is NOT an error: that is a box crossing the
    # antimeridian, the same convention geo.bbox uses.
    return [min_lon, min_lat, max_lon, max_lat]


def _resolve_bias(request):
    """Soft-bias point + scale + zoom from the query string (all optional)."""
    bias: dict = {}
    raw_lat = request.query_params.get("bias_lat")
    raw_lon = request.query_params.get("bias_lon")
    if raw_lat is not None and raw_lon is not None:
        try:
            lat, lon = float(raw_lat), float(raw_lon)
        except (TypeError, ValueError):
            raise _InvalidParam(ERR_400_INVALID_PARAMS) from None
        _require_coordinate(lat, lon)
        bias["bias_lat"], bias["bias_lon"] = lat, lon
    for name, caster in (("bias_scale", float), ("zoom", int)):
        raw = request.query_params.get(name)
        if raw is None or raw == "":
            continue
        try:
            bias[name] = caster(raw)
        except (TypeError, ValueError):
            raise _InvalidParam(ERR_400_INVALID_PARAMS) from None
    return bias


def _resolve_nearest(request):
    """``?nearest=N`` — how many known Location rows to return (0 = none)."""
    raw = request.query_params.get("nearest")
    if raw is None or raw == "":
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        raise _InvalidParam(ERR_400_INVALID_PARAMS) from None


def _extra_params(request):
    return {
        key: value
        for key, value in request.query_params.items()
        if key not in _RESERVED
    }


class _GeocodeView(StapelAPIView):
    """Shared guard + serializer seam for every geocoder proxy verb.

    ``permission_classes`` is resolved from ``STAPEL_GEO
    ["GEOCODER_PERMISSIONS"]`` at request time rather than pinned at
    import, so a host opens (or tightens) the proxy from settings without
    subclassing four views. Setting ``permission_classes`` on a subclass
    still wins — the setting is the default, not a ceiling.

    The serializer seam and the thin-view helpers come from
    ``stapel_core.django.api.views.StapelAPIView`` (core 0.41+), which
    hoisted the mixin every module used to redeclare.
    """

    throttle_classes = [GeocodingThrottle]
    throttle_scope = "geocoding"
    response_serializer_class = GeocodeResponseSerializer

    #: ``None`` means "ask the settings"; a list pins the view.
    permission_classes = None

    def get_permissions(self):
        if self.permission_classes is not None:
            return super().get_permissions()
        from django.utils.module_loading import import_string

        from ..conf import geo_settings

        return [
            import_string(dotted_path)()
            for dotted_path in (geo_settings.GEOCODER_PERMISSIONS or [])
        ]


@extend_schema(tags=["Geocoding"])
class GeocodeSearchView(_GeocodeView):
    """Forward geocoding — search places by free-text query."""

    @extend_schema(
        summary="Search places by text",
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, required=True, description="Search query"),
            OpenApiParameter("lang", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False),
            OpenApiParameter(
                "bbox", OpenApiTypes.STR, required=False,
                description="Hard restriction 'min_lon,min_lat,max_lon,max_lat'; "
                            "defaults to STAPEL_GEO['MAP_BBOX'].",
            ),
            OpenApiParameter("bias_lat", OpenApiTypes.FLOAT, required=False,
                             description="Soft bias latitude (the map's centre)."),
            OpenApiParameter("bias_lon", OpenApiTypes.FLOAT, required=False,
                             description="Soft bias longitude (the map's centre)."),
            OpenApiParameter("bias_scale", OpenApiTypes.FLOAT, required=False,
                             description="Bias strength, 0.0-1.0."),
            OpenApiParameter("zoom", OpenApiTypes.INT, required=False,
                             description="Map zoom the bias is scaled against."),
        ],
        responses={200: GeocodeResponseSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=1,
               note="Free-text forward geocoding (throttled, cached, ledgered)")
    @flow_step(PICK_LOCATION, order=4,
               note="Search-as-you-type, biased to the map's own viewport")
    def get(self, request):
        query = request.query_params.get("q", "")
        try:
            bbox = _resolve_bbox(request)
            bias = _resolve_bias(request)
        except _InvalidParam as exc:
            return StapelErrorResponse(400, exc.error_key)
        try:
            response = geocode(
                "search",
                query=query,
                lang=_resolve_lang(request),
                limit=_resolve_limit(request),
                bbox=bbox,
                **bias,
                **_extra_params(request),
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return self.serialized_response(response)


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
            OpenApiParameter("radius_km", OpenApiTypes.FLOAT, required=False,
                             description="How far the provider may look for a match."),
        ],
        responses={200: GeocodeResponseSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=3,
               note="Map pin to address (reverse geocoding)")
    def get(self, request):
        try:
            lat, lon = _required_coordinate(request)
        except _InvalidParam as exc:
            return StapelErrorResponse(400, exc.error_key)
        radius_km = request.query_params.get("radius_km")
        try:
            response = geocode(
                "reverse",
                lat=lat,
                lng=lon,
                lang=_resolve_lang(request),
                limit=_resolve_limit(request),
                radius_km=float(radius_km) if radius_km else None,
                **_extra_params(request),
            )
        except (TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return self.serialized_response(response)


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
        try:
            response = geocode(
                "structured",
                lang=_resolve_lang(request),
                limit=_resolve_limit(request),
                **_extra_params(request),
            )
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return self.serialized_response(response)


@extend_schema(tags=["Geocoding"])
class GeocodeResolveView(_GeocodeView):
    """One coordinate pair in, one confirmable place out.

    The endpoint the browser's ``navigator.geolocation`` result goes
    straight to, and the one a dragged map pin goes to on drop. It answers
    with the display line, the address components, the geohash to store
    and the runner-up candidates — everything a "is this your address?"
    confirmation step renders, in one round trip.
    """

    response_serializer_class = PlaceResolutionSerializer

    @extend_schema(
        summary="Resolve a coordinate pair to a confirmable place",
        parameters=[
            OpenApiParameter("lat", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("lon", OpenApiTypes.FLOAT, required=True),
            OpenApiParameter("lang", OpenApiTypes.STR, required=False),
            OpenApiParameter("limit", OpenApiTypes.INT, required=False,
                             description="Candidates to consider (1 pick + alternatives)."),
            OpenApiParameter("nearest", OpenApiTypes.INT, required=False,
                             description="Also return N nearest known Location rows (0 = none)."),
            OpenApiParameter("radius_km", OpenApiTypes.FLOAT, required=False),
        ],
        responses={200: PlaceResolutionSerializer},
    )
    @flow_step(GEOCODE_ADDRESS, order=4,
               note="Browser position or dropped pin to a confirmable address, in one call")
    @flow_step(PICK_LOCATION, order=5,
               note="The detected position (or the dropped pin) becomes an address to confirm")
    def get(self, request):
        try:
            lat, lon = _required_coordinate(request)
            nearest = _resolve_nearest(request)
        except _InvalidParam as exc:
            return StapelErrorResponse(400, exc.error_key)
        radius_km = request.query_params.get("radius_km")
        try:
            resolution = resolve_point(
                lat,
                lon,
                lang=_resolve_lang(request),
                limit=_resolve_limit(request),
                nearest=nearest,
                radius_km=float(radius_km) if radius_km else None,
                **_extra_params(request),
            )
        except (TypeError, ValueError):
            return StapelErrorResponse(400, ERR_400_INVALID_PARAMS)
        except GeocoderError:
            return StapelErrorResponse(502, ERR_502_GEOCODER_UNAVAILABLE)
        return self.serialized_response(resolution)


__all__ = [
    "GeocodingThrottle",
    "GeocodeSearchView",
    "GeocodeReverseView",
    "GeocodeStructuredView",
    "GeocodeResolveView",
]
