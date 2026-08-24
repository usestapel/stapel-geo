"""The geocoder-provider seam.

Subclass :class:`Geocoder`, implement the three verbs, and point
``STAPEL_GEO["GEOCODER"]`` at the dotted path to swap the geocoding
backend without forking::

    class NominatimGeocoder(Geocoder):
        name = "nominatim"

        def search(self, query, *, lang=None, limit=None, **params):
            ...  # -> GeocodeResponse

        def reverse(self, lat, lng, *, lang=None, limit=None, **params):
            ...

        def structured(self, *, lang=None, limit=None, **params):
            ...

    STAPEL_GEO = {"GEOCODER": "myproject.geo.NominatimGeocoder"}

Contract: each verb returns a :class:`~stapel_geo.geocoding.dto.GeocodeResponse`
(a normalized GeoJSON FeatureCollection) and raises :class:`GeocoderError`
when the upstream provider is unreachable or returns garbage. Providers
must read configuration lazily (at call time, via ``geo_settings``), never
at import — and must not import GDAL.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .dto import GeocodeResponse


class GeocoderError(Exception):
    """The geocoding provider is unavailable or produced an unusable response."""


class Geocoder(ABC):
    """Base class for geocoding providers (Photon by default).

    Implementations are instantiated per call by
    ``stapel_geo.geocoding.service.get_geocoder`` — keep ``__init__`` cheap
    and side-effect-free.
    """

    #: Short human-readable provider name ("photon", "nominatim", ...).
    name: str = ""

    @abstractmethod
    def search(
        self,
        query: str,
        *,
        lang: str | None = None,
        limit: int | None = None,
        **params,
    ) -> GeocodeResponse:
        """Forward geocoding: free-text *query* -> matching places.

        Two narrowings are part of the FACADE (a map picker needs both, so
        they must not be provider-specific spellings), both optional:

        - ``bbox`` — ``[min_lon, min_lat, max_lon, max_lat]`` (or the same
          as a comma-joined string). A **hard** restriction: nothing
          outside the rectangle comes back.
        - ``bias_lat`` / ``bias_lon`` (+ ``bias_scale`` 0.0-1.0, ``zoom``)
          — a **soft** one: near results rank higher, far ones survive.
          A provider without a soft bias accepts and ignores these rather
          than silently promoting them to a hard filter.

        ``params`` carries anything further that is provider-specific (OSM
        tag filters, layers, ...); unknown keys are ignored by providers
        that do not understand them.
        """

    @abstractmethod
    def reverse(
        self,
        lat: float,
        lng: float,
        *,
        lang: str | None = None,
        limit: int | None = None,
        **params,
    ) -> GeocodeResponse:
        """Reverse geocoding: coordinates -> nearest place(s).

        ``radius_km`` (optional, facade-level) caps how far the provider
        may look for a match. Providers without the notion ignore it.
        """

    @abstractmethod
    def structured(
        self,
        *,
        lang: str | None = None,
        limit: int | None = None,
        **params,
    ) -> GeocodeResponse:
        """Structured search by address components (city, street, ...).

        At least one address field should be supplied via ``params``
        (``city``, ``street``, ``postcode``, ``countrycode``, ...).
        """


__all__ = ["Geocoder", "GeocoderError"]
