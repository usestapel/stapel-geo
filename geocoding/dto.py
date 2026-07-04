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
    """
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
    """
    type: str = "FeatureCollection"
    features: list[GeocodeFeature] = field(default_factory=list)


__all__ = [
    "OsmType",
    "GeocodeProperties",
    "GeocodeGeometry",
    "GeocodeFeature",
    "GeocodeResponse",
]
