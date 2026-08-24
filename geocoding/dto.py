"""Data Transfer Objects for the geocoder proxy — a normalized GeoJSON shape.

Every :class:`~stapel_geo.geocoding.base.Geocoder` returns results in this
GeoJSON ``FeatureCollection`` form regardless of the upstream provider, so
callers (and the HTTP proxy) get a stable contract. The default Photon
provider already speaks GeoJSON; other providers map their responses into
these dataclasses.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OsmType(str, Enum):
    """OpenStreetMap element type.

    Members:
        N: Node
        W: Way
        R: Relation
    """
    N = "N"
    W = "W"
    R = "R"


@dataclass
class GeocodeProperties:
    """Properties of a geocoded feature.

    Attributes:
        name: Place name. Example: Berlin
        country: Country name. Example: Germany
        countrycode: ISO 3166-1 alpha-2 code. Example: DE
        osm_key: OSM tag key. Example: place
        osm_value: OSM tag value. Example: city
        osm_type: OSM element type (N/W/R). Example: R
        osm_id: OSM element ID. Example: 240109189
        state: State or region. Example: Brandenburg
        county: County name. Example: Kreisfreie Stadt Berlin
        city: City name. Example: Berlin
        district: District or suburb. Example: Mitte
        street: Street name. Example: Unter den Linden
        housenumber: House number. Example: 1
        postcode: Postal code. Example: 10117
        extent: Bounding box [minLon, minLat, maxLon, maxLat]. Example: [13.08, 52.33, 13.76, 52.68]
        formatted: One-line human label built by STAPEL_GEO["ADDRESS_FORMATTER"]. Example: Unter den Linden, 1, Berlin, Germany
    """
    formatted: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    countrycode: Optional[str] = None
    osm_key: Optional[str] = None
    osm_value: Optional[str] = None
    osm_type: Optional[str] = None
    osm_id: Optional[int] = None
    state: Optional[str] = None
    county: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    street: Optional[str] = None
    housenumber: Optional[str] = None
    postcode: Optional[str] = None
    extent: Optional[list[float]] = None


@dataclass
class GeocodeGeometry:
    """GeoJSON point geometry.

    Attributes:
        type: Geometry type. Example: Point
        coordinates: [longitude, latitude]. Example: [13.38333, 52.51667]
    """
    type: str
    coordinates: list[float]


@dataclass
class GeocodeFeature:
    """A single geocoded result feature.

    Attributes:
        type: GeoJSON type. Example: Feature
        geometry: Point geometry with coordinates.
        properties: Place properties (name, address components, OSM data).
    """
    type: str
    geometry: GeocodeGeometry
    properties: GeocodeProperties


@dataclass
class GeocodeResponse:
    """GeoJSON FeatureCollection with geocoding results.

    Attributes:
        type: GeoJSON type. Example: FeatureCollection
        features: List of geocoded features.
        lang: Language actually asked of the provider after clamping (may differ from the requested one). Example: default
    """
    type: str = "FeatureCollection"
    features: list[GeocodeFeature] = field(default_factory=list)
    lang: Optional[str] = None


@dataclass
class PlaceSummary:
    """A known ``Location`` row near a resolved point (reference data).

    Attributes:
        uuid: Cross-service location UUID. Example: 550e8400-e29b-41d4-a716-446655440000
        name: Location name. Example: Berlin
        country: Country name. Example: Germany
        display_name: Human label of the tree node. Example: Berlin (City in Germany)
        distance_km: Great-circle distance from the resolved point. Example: 1.42
    """
    uuid: str
    name: Optional[str] = None
    country: str = ""
    display_name: str = ""
    distance_km: Optional[float] = None


@dataclass
class PlaceResolution:
    """Everything a location picker needs to CONFIRM one point, in one call.

    The answer to "the browser gave me a coordinate / the user dropped a
    pin — now what do I show them?". One round trip: reverse geocoding,
    the display line, the address components, the alternatives to offer if
    the top pick is wrong, the geohash to store, and (opt-in) the nearest
    known locations from the tree.

    Attributes:
        lat: Latitude that was resolved (echoed, so the client can match the answer to its request). Example: 52.51667
        lon: Longitude that was resolved. Example: 13.38333
        geohash: Geohash of the point at STAPEL_GEO["GEOHASH_PRECISION"] — what a consumer stores. Example: u33dc0cp
        lang: Language actually used upstream after clamping. Example: default
        formatted: One-line human label of the best candidate. Example: Unter den Linden, 1, Berlin, Germany
        address: Address components of the best candidate.
        feature: The best candidate as a GeoJSON feature (its coordinates are the geocoder's snapped point, which may differ from lat/lon).
        alternatives: Further candidates, best-first, for a "not this one?" list.
        nearest: Known Location rows near the point (only when ``nearest`` was requested).
    """
    lat: float
    lon: float
    geohash: str
    lang: Optional[str] = None
    formatted: Optional[str] = None
    address: Optional[GeocodeProperties] = None
    feature: Optional[GeocodeFeature] = None
    alternatives: list[GeocodeFeature] = field(default_factory=list)
    nearest: list[PlaceSummary] = field(default_factory=list)


__all__ = [
    "OsmType",
    "GeocodeProperties",
    "GeocodeGeometry",
    "GeocodeFeature",
    "GeocodeResponse",
    "PlaceSummary",
    "PlaceResolution",
]
