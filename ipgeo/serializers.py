"""Serializer for the IP-location response."""
from stapel_core.django.api.serializers import StapelDataclassSerializer

from .dto import IpLocation


class IpLocationSerializer(StapelDataclassSerializer):
    class Meta:
        dataclass = IpLocation


__all__ = ["IpLocationSerializer"]
