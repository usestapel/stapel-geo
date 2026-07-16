"""Serializers for the stapel-geo location API (flat, GDAL-free)."""
from rest_framework import serializers
from stapel_core.django.api.serializers import StapelDataclassSerializer

from .dto import ValidateUuidResponse
from .models import Location


class LocationCompactSerializer(serializers.ModelSerializer):
    """Lightweight Location representation; nearby adds distance_km."""

    distance_km = serializers.FloatField(read_only=True, required=False, allow_null=True)

    class Meta:
        model = Location
        fields = [
            "id", "uuid", "name", "type", "country", "geohash",
            "tn_parent", "display_name_narrow", "display_name_broad", "distance_km",
        ]


class LocationSerializer(serializers.ModelSerializer):
    """Full Location representation — a flat point plus tree metadata."""

    class Meta:
        model = Location
        fields = [
            "id", "uuid", "name", "type", "country", "lat", "lon", "geohash",
            "tn_parent", "display_name_narrow", "display_name_broad",
        ]
        read_only_fields = ["geohash", "display_name_narrow", "display_name_broad"]


class ValidateUuidResponseSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = ValidateUuidResponse


__all__ = [
    "LocationCompactSerializer",
    "LocationSerializer",
    "ValidateUuidResponseSerializer",
]
