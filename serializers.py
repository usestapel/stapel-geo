"""Serializers for the stapel-geo spatial API (loaded only with the app).

Geometry fields are rendered as GeoJSON via method fields, so no
``djangorestframework-gis`` dependency is required for the read API. This
module imports the GeoDjango models — it is part of the spatial layer.
"""
import json

from rest_framework import serializers
from stapel_core.django.api.serializers import StapelDataclassSerializer

from .dto import ValidateUuidResponse
from .models import GeoFile, Location


class LocationCompactSerializer(serializers.ModelSerializer):
    """Lightweight Location representation (no geometry); nearby adds distance."""

    distance_km = serializers.FloatField(read_only=True, required=False, allow_null=True)

    class Meta:
        model = Location
        fields = [
            "id", "uuid", "g_id", "name", "type", "country", "geohash",
            "tn_parent", "display_name_narrow", "display_name_broad", "distance_km",
        ]


class LocationSerializer(serializers.ModelSerializer):
    """Full Location representation with GeoJSON geometry and centroid."""

    geometry = serializers.SerializerMethodField()
    center = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = [
            "id", "uuid", "g_id", "name", "type", "varname", "country",
            "geometry", "center", "geohash", "iso_code", "hasc_code",
            "tn_parent", "display_name_narrow", "display_name_broad",
        ]

    def _geojson(self, geom):
        return json.loads(geom.geojson) if geom else None

    def get_geometry(self, obj):
        return self._geojson(obj.geometry)

    def get_center(self, obj):
        return self._geojson(obj.center)


class GeoFileSerializer(serializers.ModelSerializer):
    progress_percent = serializers.SerializerMethodField()

    class Meta:
        model = GeoFile
        fields = [
            "id", "geo_json", "added", "location_level", "validation_result",
            "import_status", "import_progress", "import_total", "import_error",
            "progress_percent",
        ]
        read_only_fields = [
            "validation_result", "location_level", "added",
            "import_status", "import_progress", "import_total", "import_error",
        ]

    def get_progress_percent(self, obj):
        if obj.import_total == 0:
            return 0
        return round((obj.import_progress / obj.import_total) * 100, 1)


class ValidateUuidResponseSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = ValidateUuidResponse


__all__ = [
    "LocationCompactSerializer",
    "LocationSerializer",
    "GeoFileSerializer",
    "ValidateUuidResponseSerializer",
]
