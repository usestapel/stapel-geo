"""Dataclass DTOs — API models of stapel-geo that are not ORM instances.

Location/GeoFile responses are DRF ``ModelSerializer`` output; these
dataclasses cover the non-model responses (UUID validation). GDAL-free.
"""
from dataclasses import dataclass


@dataclass
class ValidateUuidResponse:
    """UUID validation result for cross-service reference checks.

    Attributes:
        valid: Whether the UUID exists. Example: true
        uuid: The validated UUID string. Example: 550e8400-e29b-41d4-a716-446655440000
    """

    valid: bool
    uuid: str


__all__ = ["ValidateUuidResponse"]
