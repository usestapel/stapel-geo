"""Canonical-prefix URLconf for contract emission (contract-pipeline.md §2).

The host mounts geo at ``path("geo/", include("stapel_geo.urls"))``, which
yields the canonical versioned surface ``/geo/api/v1/...``
(api-versioning.md §2 — the version segment is part of the contract).
This URLconf reproduces that mount exactly, so drf-spectacular emits
``/geo/api/v1/...`` paths (and matching ``geo_api_v1_*`` operationIds) and
``generate_flow_docs`` resolves flow endpoints to the same.
"""
from django.conf.urls import include
from django.urls import path

urlpatterns = [
    path("geo/", include("stapel_geo.urls")),
]
