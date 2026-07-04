"""Serializers for the geocoder proxy responses (GDAL-free)."""
from stapel_core.django.api.serializers import StapelDataclassSerializer

from .dto import GeocodeResponse


class GeocodeResponseSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = GeocodeResponse


__all__ = ["GeocodeResponseSerializer"]
