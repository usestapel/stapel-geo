"""Serializers for the geocoder proxy responses (GDAL-free)."""
from stapel_core.django.api.serializers import StapelDataclassSerializer

from .dto import GeocodeResponse, PlaceResolution


class GeocodeResponseSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = GeocodeResponse


class PlaceResolutionSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = PlaceResolution


__all__ = ["GeocodeResponseSerializer", "PlaceResolutionSerializer"]
