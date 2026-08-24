"""Built-in geocoder providers + the provider merge-registry.

Registry semantics (the ``stapel-agent`` PROVIDERS pattern):
``registered_geocoders()`` = ``BUILTIN_GEOCODERS`` <- ``STAPEL_GEO
["GEOCODERS"]`` (settings merge; ``None``/``""`` removes a name) <-
``register_geocoder()`` runtime registrations. ``STAPEL_GEO["GEOCODER"]``
selects the default **name**.

Built-ins:

- ``photon`` — :class:`PhotonGeocoder`, the production default (self-
  hosted Photon, https://photon.komoot.io, speaks GeoJSON natively).
- ``nominatim`` — :class:`NominatimGeocoder`, a real second provider on
  the public OSM API. **Dev/fallback only**: the public instance enforces
  an absolute 1 request/second policy (self-enforced here) and forbids
  heavy production use — self-host Nominatim or use Photon for traffic.
- ``google`` / ``yandex`` — key-gated stubs: paid APIs whose keys are the
  host's own (the same PAYG discipline as LLM keys in stapel-agent — no
  bundled keys, ever). Each method raises ``NotImplementedError`` with a
  pointer; implement against the official API and register your subclass.

Configuration is read lazily from ``geo_settings`` at call time — never
at import. This module imports ``requests`` and nothing heavier.
"""
from __future__ import annotations

import logging
import threading
import time

import requests

from ..conf import geo_settings
from .base import Geocoder, GeocoderError
from .dto import GeocodeFeature, GeocodeGeometry, GeocodeProperties, GeocodeResponse
from .format import apply_formatter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Photon (production default)
# ---------------------------------------------------------------------------


class PhotonGeocoder(Geocoder):
    """Proxy a self-hosted Photon instance (the framework default)."""

    name = "photon"

    def _base_url(self) -> str:
        return geo_settings.PHOTON_URL.rstrip("/")

    def _timeout(self) -> int:
        return geo_settings.GEOCODER_TIMEOUT

    def resolve_language(self, lang: str | None) -> str | None:
        """Clamp *lang* to a language the configured Photon bundle indexes.

        Photon does **not** degrade gracefully here. Ask it for a language
        its index was not built with and it answers HTTP 400 with a body
        like ``{"lang":[{"message":"Language is not supported. Supported
        are: default, de, en, fr","value":"ru"}]}`` — its documented
        "falls back to ``-default-language``" behaviour is about a
        *supported* language with a missing translation, not about a
        language the index never had. So the clamp is mandatory, and what
        it clamps *to* is the whole ballgame:

        - an exact match is forwarded as-is;
        - a regional tag is retried on its base subtag (``ru-RU`` -> ``ru``,
          ``pt_BR`` -> ``pt``) — an ``Accept-Language`` header is normally
          regional and would otherwise never match;
        - anything left over goes to ``PHOTON_LANGUAGE_FALLBACK``, whose
          default ``"default"`` is Photon's LOCAL-NAME mode. That is the
          fix for the bug this replaced: the old code clamped to ``"en"``,
          so a Russian product asking for ``lang=ru`` against a stock
          GraphHopper dump silently received *English* street names — no
          error, no log line, wrong answer. ``default`` returns
          "Тверская улица" where ``en`` returned "Tverskaya Street".

        ``None`` is passed through untouched so Photon applies its own
        default. The language actually sent is echoed back on
        :attr:`GeocodeResponse.lang` so a caller can see the clamp happen.
        """
        if lang is None:
            return None
        supported = {str(code) for code in (geo_settings.PHOTON_LANGUAGES or [])}
        if lang in supported:
            return lang
        base = str(lang).replace("_", "-").split("-")[0].lower()
        if base in supported:
            return base
        return geo_settings.PHOTON_LANGUAGE_FALLBACK or None

    def _get(self, path: str, params: dict) -> GeocodeResponse:
        cleaned = {k: v for k, v in params.items() if v is not None}
        try:
            resp = requests.get(
                f"{self._base_url()}{path}", params=cleaned, timeout=self._timeout()
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.HTTPError as exc:
            # Photon puts the REASON in the body (unsupported language,
            # malformed bbox, ...). Swallowing it leaves a bare 502 and no
            # way to tell a misconfiguration from an outage.
            detail = ""
            try:
                detail = f" body={exc.response.text[:300]!r}"
            except Exception:  # noqa: BLE001 — diagnostics are best-effort
                pass
            raise GeocoderError(
                f"Photon request to {path} failed: {exc}{detail}"
            ) from exc
        except requests.RequestException as exc:
            raise GeocoderError(f"Photon request to {path} failed: {exc}") from exc
        except ValueError as exc:  # non-JSON body
            raise GeocoderError(f"Photon returned a non-JSON response: {exc}") from exc
        response = _parse_geojson(payload)
        response.lang = cleaned.get("lang")
        return response

    def search(
        self,
        query,
        *,
        lang=None,
        limit=None,
        bbox=None,
        bias_lat=None,
        bias_lon=None,
        bias_scale=None,
        zoom=None,
        **params,
    ):
        """Forward geocoding, with the two map-shaped narrowings Photon offers.

        ``bbox`` (``[min_lon, min_lat, max_lon, max_lat]``) is a hard
        restriction — results outside the rectangle are not returned at
        all. ``bias_lat``/``bias_lon`` (+ optional ``bias_scale`` 0.0-1.0
        and ``zoom``) are a soft one: results near the point rank higher
        but distant matches still appear. A map picker wants the bias
        (the user's viewport) and a country-scoped product wants the
        bbox; they compose.
        """
        return self._get(
            "/api",
            {
                "q": query,
                "lang": self.resolve_language(lang),
                "limit": limit,
                "bbox": _bbox_param(bbox),
                "lat": bias_lat,
                "lon": bias_lon,
                "location_bias_scale": bias_scale,
                "zoom": zoom,
                **params,
            },
        )

    def reverse(self, lat, lng, *, lang=None, limit=None, radius_km=None, **params):
        return self._get(
            "/reverse",
            {
                "lat": lat,
                "lon": lng,
                "lang": self.resolve_language(lang),
                "limit": limit,
                "radius": radius_km,
                **params,
            },
        )

    def structured(self, *, lang=None, limit=None, **params):
        return self._get(
            "/structured",
            {"lang": self.resolve_language(lang), "limit": limit, **params},
        )


# ---------------------------------------------------------------------------
# Nominatim (public OSM API — dev/fallback, 1 rps)
# ---------------------------------------------------------------------------

# Public-instance politeness: nominatim.openstreetmap.org's usage policy is
# an absolute maximum of 1 request per second. Enforced process-locally so a
# burst of proxy calls cannot get the host's IP banned.
_NOMINATIM_MIN_INTERVAL_S = 1.0
_nominatim_lock = threading.Lock()
_nominatim_last_call = 0.0

# Nominatim structured-search fields (its own parameter names). The generic
# ``structured()`` extras are passed through; Photon-style names are mapped.
_NOMINATIM_STRUCTURED_MAP = {
    "countrycode": "country",
    "housenumber": "street",  # merged with street below when both are given
}


class NominatimGeocoder(Geocoder):
    """Public OSM Nominatim (https://nominatim.openstreetmap.org).

    A real, keyless second provider — **for development and as a
    fallback**, not as a production default: the public instance's usage
    policy is 1 request/second (self-enforced here), requires a
    descriptive ``User-Agent``, and prohibits heavy autocomplete-style
    traffic. Self-host Nominatim (or keep Photon) for production.
    """

    name = "nominatim"

    def _base_url(self) -> str:
        return geo_settings.NOMINATIM_URL.rstrip("/")

    def _get(self, path: str, params: dict) -> GeocodeResponse:
        global _nominatim_last_call
        cleaned = {k: v for k, v in params.items() if v is not None}
        cleaned["format"] = "geojson"
        cleaned["addressdetails"] = 1
        with _nominatim_lock:
            wait = _NOMINATIM_MIN_INTERVAL_S - (time.monotonic() - _nominatim_last_call)
            if wait > 0:
                time.sleep(wait)
            _nominatim_last_call = time.monotonic()
        try:
            resp = requests.get(
                f"{self._base_url()}{path}",
                params=cleaned,
                timeout=geo_settings.GEOCODER_TIMEOUT,
                headers={"User-Agent": "stapel-geo (+https://github.com/usestapel/stapel-geo)"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise GeocoderError(f"Nominatim request to {path} failed: {exc}") from exc
        except ValueError as exc:
            raise GeocoderError(f"Nominatim returned a non-JSON response: {exc}") from exc
        response = _parse_nominatim(payload)
        response.lang = cleaned.get("accept-language")
        return response

    def search(
        self,
        query,
        *,
        lang=None,
        limit=None,
        bbox=None,
        bias_lat=None,
        bias_lon=None,
        bias_scale=None,
        zoom=None,
        **params,
    ):
        """Forward geocoding. ``bbox`` becomes a bounded ``viewbox``.

        Nominatim has no soft location bias, so ``bias_lat``/``bias_lon``/
        ``bias_scale``/``zoom`` are accepted (the facade's verb signature is
        provider-agnostic) and ignored — a bias that silently became a hard
        restriction would drop results the caller asked to merely rank lower.
        """
        narrowing = {}
        rendered = _bbox_param(bbox)
        if rendered:
            narrowing["viewbox"] = rendered
            narrowing["bounded"] = 1
        return self._get(
            "/search",
            {
                "q": query,
                "accept-language": lang,
                "limit": limit,
                **narrowing,
                **params,
            },
        )

    def reverse(self, lat, lng, *, lang=None, limit=None, radius_km=None, **params):
        # /reverse returns a single result; limit and radius do not apply.
        return self._get(
            "/reverse", {"lat": lat, "lon": lng, "accept-language": lang, **params}
        )

    def structured(self, *, lang=None, limit=None, **params):
        mapped = {}
        for key, value in params.items():
            mapped[_NOMINATIM_STRUCTURED_MAP.get(key, key)] = value
        if "housenumber" in params and "street" in params:
            mapped["street"] = f"{params['housenumber']} {params['street']}"
        return self._get(
            "/search", {"accept-language": lang, "limit": limit, **mapped}
        )


# ---------------------------------------------------------------------------
# Key-gated stubs (host brings its own key — PAYG discipline)
# ---------------------------------------------------------------------------


class GoogleGeocoder(Geocoder):
    """Stub for the Google Geocoding API (paid, key-gated).

    Not implemented: Google's key belongs to the host (PAYG discipline —
    stapel never bundles metered keys). Implement against
    https://developers.google.com/maps/documentation/geocoding (forward =
    ``address=``, reverse = ``latlng=``, components for structured), read
    the key from your own settings, map the response into
    :class:`GeocodeResponse`, then register your subclass::

        STAPEL_GEO = {"GEOCODERS": {"google": "myproject.geo.MyGoogleGeocoder"},
                      "GEOCODER": "google"}
    """

    name = "google"

    _HINT = (
        "GoogleGeocoder is a key-gated stub — implement it with your own "
        "Google Geocoding API key (see the class docstring) and register "
        "the subclass via STAPEL_GEO['GEOCODERS']."
    )

    def search(self, query, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)

    def structured(self, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)


class YandexGeocoder(Geocoder):
    """Stub for the Yandex Geocoder API (paid, key-gated).

    Not implemented: the API key belongs to the host. Implement against
    https://yandex.com/maps-api/docs/geocoder-api/ (``geocode=`` forward and
    reverse, ``apikey=`` from your own settings), map the response into
    :class:`GeocodeResponse`, then register your subclass via
    ``STAPEL_GEO["GEOCODERS"]`` (see :class:`GoogleGeocoder` for the shape).
    """

    name = "yandex"

    _HINT = (
        "YandexGeocoder is a key-gated stub — implement it with your own "
        "Yandex Geocoder API key (see the class docstring) and register "
        "the subclass via STAPEL_GEO['GEOCODERS']."
    )

    def search(self, query, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)

    def structured(self, *, lang=None, limit=None, **params):
        raise NotImplementedError(self._HINT)


# ---------------------------------------------------------------------------
# Provider registry (merge-over-builtins, the stapel-agent PROVIDERS pattern)
# ---------------------------------------------------------------------------

BUILTIN_GEOCODERS: dict[str, str] = {
    "photon": "stapel_geo.geocoding.providers.PhotonGeocoder",
    "nominatim": "stapel_geo.geocoding.providers.NominatimGeocoder",
    "google": "stapel_geo.geocoding.providers.GoogleGeocoder",
    "yandex": "stapel_geo.geocoding.providers.YandexGeocoder",
}

_runtime_geocoders: dict[str, str | None] = {}


def register_geocoder(name: str, dotted_path: str | None) -> None:
    """Register (or, with ``None``/``""``, unregister) a provider at runtime.

    Runtime registrations win over both ``STAPEL_GEO["GEOCODERS"]`` and the
    built-ins — the same precedence as ``stapel-agent.register_provider``.
    """
    _runtime_geocoders[name] = dotted_path


def registered_geocoders() -> dict[str, str]:
    """The effective name -> dotted-path registry.

    ``BUILTIN_GEOCODERS`` merged under ``STAPEL_GEO["GEOCODERS"]`` merged
    under runtime :func:`register_geocoder` entries; a ``None``/``""``
    value at any layer removes the name.
    """
    merged: dict[str, str | None] = dict(BUILTIN_GEOCODERS)
    merged.update(geo_settings.GEOCODERS or {})
    merged.update(_runtime_geocoders)
    return {name: path for name, path in merged.items() if path}


# ---------------------------------------------------------------------------
# Response mapping helpers
# ---------------------------------------------------------------------------


def _bbox_param(bbox) -> str | None:
    """Render a bbox as the ``min_lon,min_lat,max_lon,max_lat`` string.

    Accepts the sequence form (what settings and the HTTP layer carry) or a
    ready-made string (what a caller passing through raw extras sends).
    """
    if bbox is None or bbox == "":
        return None
    if isinstance(bbox, str):
        return bbox
    return ",".join(str(value) for value in bbox)


def _parse_geojson(payload: dict) -> GeocodeResponse:
    """Map a Photon-style GeoJSON FeatureCollection into the normalized DTO."""
    features: list[GeocodeFeature] = []
    for raw in payload.get("features", []) or []:
        geometry = raw.get("geometry") or {}
        props = raw.get("properties") or {}
        features.append(
            GeocodeFeature(
                type=raw.get("type", "Feature"),
                geometry=GeocodeGeometry(
                    type=geometry.get("type", "Point"),
                    coordinates=geometry.get("coordinates", []),
                ),
                properties=apply_formatter(
                    GeocodeProperties(
                        **{
                            key: props.get(key)
                            for key in GeocodeProperties.__dataclass_fields__
                            if key != "formatted"
                        }
                    )
                ),
            )
        )
    return GeocodeResponse(
        type=payload.get("type", "FeatureCollection"), features=features
    )


def _parse_nominatim(payload: dict) -> GeocodeResponse:
    """Map a Nominatim ``format=geojson`` response into the normalized DTO.

    Nominatim's GeoJSON keeps the address split under ``properties.
    address`` and the OSM identity under ``osm_type``/``osm_id``; both are
    flattened into :class:`GeocodeProperties` (osm_type normalized to
    N/W/R like Photon).
    """
    osm_type_map = {"node": "N", "way": "W", "relation": "R"}
    features: list[GeocodeFeature] = []
    for raw in payload.get("features", []) or []:
        geometry = raw.get("geometry") or {}
        props = raw.get("properties") or {}
        address = props.get("address") or {}
        bbox = raw.get("bbox")
        features.append(
            GeocodeFeature(
                type=raw.get("type", "Feature"),
                geometry=GeocodeGeometry(
                    type=geometry.get("type", "Point"),
                    coordinates=geometry.get("coordinates", []),
                ),
                properties=apply_formatter(GeocodeProperties(
                    name=props.get("name") or props.get("display_name"),
                    country=address.get("country"),
                    countrycode=(address.get("country_code") or "").upper() or None,
                    osm_key=props.get("category"),
                    osm_value=props.get("type"),
                    osm_type=osm_type_map.get(props.get("osm_type")),
                    osm_id=props.get("osm_id"),
                    state=address.get("state"),
                    county=address.get("county"),
                    city=address.get("city") or address.get("town") or address.get("village"),
                    district=address.get("suburb") or address.get("city_district"),
                    street=address.get("road"),
                    housenumber=address.get("house_number"),
                    postcode=address.get("postcode"),
                    extent=list(bbox) if bbox else None,
                )),
            )
        )
    return GeocodeResponse(
        type=payload.get("type", "FeatureCollection"), features=features
    )


__all__ = [
    "PhotonGeocoder",
    "NominatimGeocoder",
    "GoogleGeocoder",
    "YandexGeocoder",
    "BUILTIN_GEOCODERS",
    "register_geocoder",
    "registered_geocoders",
]
