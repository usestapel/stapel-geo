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

        An unsupported (or missing) language falls back to English; ``None``
        is passed through so Photon applies its own default.
        """
        if lang is None:
            return None
        supported = set(geo_settings.PHOTON_LANGUAGES)
        return lang if lang in supported else "en"

    def _get(self, path: str, params: dict) -> GeocodeResponse:
        cleaned = {k: v for k, v in params.items() if v is not None}
        try:
            resp = requests.get(
                f"{self._base_url()}{path}", params=cleaned, timeout=self._timeout()
            )
            resp.raise_for_status()
            payload = resp.json()
        except requests.RequestException as exc:
            raise GeocoderError(f"Photon request to {path} failed: {exc}") from exc
        except ValueError as exc:  # non-JSON body
            raise GeocoderError(f"Photon returned a non-JSON response: {exc}") from exc
        return _parse_geojson(payload)

    def search(self, query, *, lang=None, limit=None, **params):
        return self._get(
            "/api",
            {"q": query, "lang": self.resolve_language(lang), "limit": limit, **params},
        )

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        return self._get(
            "/reverse",
            {
                "lat": lat,
                "lon": lng,
                "lang": self.resolve_language(lang),
                "limit": limit,
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
        return _parse_nominatim(payload)

    def search(self, query, *, lang=None, limit=None, **params):
        return self._get(
            "/search",
            {"q": query, "accept-language": lang, "limit": limit, **params},
        )

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        # /reverse returns a single result; limit does not apply.
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
                properties=GeocodeProperties(
                    **{
                        key: props.get(key)
                        for key in GeocodeProperties.__dataclass_fields__
                    }
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
                properties=GeocodeProperties(
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
                ),
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
