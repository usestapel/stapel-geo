"""Geocoder proxy — a provider seam over an external geocoding service.

The default provider proxies a self-hosted Photon instance, but any
provider (Nominatim, Google, Mapbox, ...) can be dropped in by pointing
``STAPEL_GEO["GEOCODER"]`` at a :class:`~stapel_geo.geocoding.base.Geocoder`
subclass. Nothing here imports GDAL — geocoding is pure HTTP + dataclasses.
"""
