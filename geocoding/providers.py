"""Built-in geocoder providers. Default: :class:`PhotonGeocoder`.

Photon (https://photon.komoot.io) is a self-hostable OSM geocoder that
already speaks GeoJSON, so mapping its response into
:class:`~stapel_geo.geocoding.dto.GeocodeResponse` is nearly one-to-one.

Configuration is read lazily from ``geo_settings`` at call time
(``PHOTON_URL``, ``PHOTON_LANGUAGES``, ``GEOCODER_TIMEOUT``) — never at
import. This module imports ``requests`` but never GDAL.
"""
from __future__ import annotations

import logging

import requests

from ..conf import geo_settings
from .base import Geocoder, GeocoderError
from .dto import GeocodeFeature, GeocodeGeometry, GeocodeProperties, GeocodeResponse

logger = logging.getLogger(__name__)


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
        return self._parse(payload)

    def _parse(self, payload: dict) -> GeocodeResponse:
        """Map a Photon GeoJSON FeatureCollection into the normalized DTO."""
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


__all__ = ["PhotonGeocoder"]
