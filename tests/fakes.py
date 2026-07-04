"""Test doubles for the geocoder seam and the import status machine."""
from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import Optional

from stapel_geo.geocoding.base import Geocoder, GeocoderError
from stapel_geo.geocoding.dto import (
    GeocodeFeature,
    GeocodeGeometry,
    GeocodeProperties,
    GeocodeResponse,
)


def _feature(name: str, lon: float, lat: float) -> GeocodeFeature:
    return GeocodeFeature(
        type="Feature",
        geometry=GeocodeGeometry(type="Point", coordinates=[lon, lat]),
        properties=GeocodeProperties(name=name, country="Testland", countrycode="TL"),
    )


class FakeGeocoder(Geocoder):
    """Deterministic geocoder — swapped in via STAPEL_GEO['GEOCODER']."""

    name = "fake"

    def search(self, query, *, lang=None, limit=None, **params):
        return GeocodeResponse(features=[_feature(query, 6.13, 49.61)])

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        return GeocodeResponse(features=[_feature("reversed", lng, lat)])

    def structured(self, *, lang=None, limit=None, **params):
        city = params.get("city", "structured")
        return GeocodeResponse(features=[_feature(city, 6.13, 49.61)])


class FailingGeocoder(Geocoder):
    """Always raises GeocoderError — exercises the 502 degradation path."""

    name = "failing"

    def search(self, query, *, lang=None, limit=None, **params):
        raise GeocoderError("boom")

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        raise GeocoderError("boom")

    def structured(self, *, lang=None, limit=None, **params):
        raise GeocoderError("boom")


class NotAGeocoder:
    """Importable, but not a Geocoder subclass (checks.W002)."""


@dataclass
class NearbyCandidate:
    """Minimal Location stand-in for geohash ranking / service tests."""

    uuid: str
    name: str
    country: str
    geohash: Optional[str]
    type: str = "City"

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.type} in {self.country})"


class FakeGeoFile:
    """Duck-typed GeoFile for the GDAL-free import status-machine tests.

    Records every ``save(update_fields=...)`` so tests can assert the exact
    transition sequence.
    """

    def __init__(self, features_json: dict | str, *, file_id=1):
        if isinstance(features_json, dict):
            features_json = json.dumps(features_json)
        self._raw = features_json.encode("utf-8")
        self.id = file_id
        self.import_status = "pending"
        self.import_progress = 0
        self.import_total = 0
        self.import_error = ""
        self.location_level = 0
        self.validation_result = ""
        self.saved_fields: list[list[str]] = []

    def open_geojson(self):
        return io.BytesIO(self._raw)

    def save(self, *args, update_fields=None, **kwargs):
        self.saved_fields.append(list(update_fields) if update_fields else [])
