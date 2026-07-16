"""Test doubles for the geocoder seam, the search facade and geohash math."""
from __future__ import annotations

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
    """Deterministic geocoder — registered via STAPEL_GEO['GEOCODERS']."""

    name = "fake"

    def search(self, query, *, lang=None, limit=None, **params):
        return GeocodeResponse(features=[_feature(query, 6.13, 49.61)])

    def reverse(self, lat, lng, *, lang=None, limit=None, **params):
        return GeocodeResponse(features=[_feature("reversed", lng, lat)])

    def structured(self, *, lang=None, limit=None, **params):
        city = params.get("city", "structured")
        return GeocodeResponse(features=[_feature(city, 6.13, 49.61)])


class CountingGeocoder(FakeGeocoder):
    """FakeGeocoder that counts upstream calls (cache-hit assertions)."""

    calls = 0

    def search(self, query, *, lang=None, limit=None, **params):
        type(self).calls += 1
        return super().search(query, lang=lang, limit=limit, **params)


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


class NotASearchBackend:
    """Importable, but missing the facade verbs (checks.W004)."""


@dataclass
class NearbyCandidate:
    """Minimal Location stand-in for geohash ranking tests (pure math)."""

    uuid: str
    name: str
    country: str
    geohash: Optional[str]
    type: str = "City"

    @property
    def display_name(self) -> str:
        return f"{self.name} ({self.type} in {self.country})"


class FakeRedisGeo:
    """Tiny in-memory stand-in for the redis-py GEO commands.

    Implements just enough (``geoadd``/``geosearch``/``zrem``/``delete``)
    for RedisGeoSearchBackend unit tests, with haversine distances so
    radius/nearby ordering is realistic.
    """

    def __init__(self):
        self.points: dict[str, tuple[float, float]] = {}  # member -> (lon, lat)

    # -- redis-py surface -------------------------------------------------

    def geoadd(self, key, values):
        lon, lat, member = values
        self.points[str(member)] = (lon, lat)
        return 1

    def zrem(self, key, member):
        return 1 if self.points.pop(str(member), None) is not None else 0

    def delete(self, key):
        self.points.clear()
        return 1

    def geosearch(
        self,
        key,
        *,
        longitude=None,
        latitude=None,
        radius=None,
        width=None,
        height=None,
        unit="km",
        withdist=False,
        sort=None,
        count=None,
    ):
        import math

        def haversine_km(lat1, lon1, lat2, lon2):
            r = 6371.0
            p1, p2 = math.radians(lat1), math.radians(lat2)
            dp = math.radians(lat2 - lat1)
            dl = math.radians(lon2 - lon1)
            a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
            return 2 * r * math.asin(math.sqrt(a))

        hits = []
        for member, (lon, lat) in self.points.items():
            dist = haversine_km(latitude, longitude, lat, lon)
            if radius is not None:
                if dist <= radius:
                    hits.append((member, dist))
            else:
                # BYBOX: approximate the box in km around the centre, with
                # longitude wrapping — mirrors what the backend asks for.
                dlat_km = abs(lat - latitude) * 111.32
                dlon = abs((lon - longitude + 180) % 360 - 180)
                dlon_km = dlon * 111.32 * math.cos(math.radians(latitude))
                if dlat_km <= height / 2 and dlon_km <= width / 2:
                    hits.append((member, dist))
        if sort == "ASC":
            hits.sort(key=lambda pair: pair[1])
        if count is not None:
            hits = hits[:count]
        if withdist:
            return [(m.encode(), d) for m, d in hits]
        return [m.encode() for m, _ in hits]
