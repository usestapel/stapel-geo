"""Root URLconf — mounts the canonical versioned API (api-versioning.md §2).

The host project mounts this module at its prefix::

    path("geo/", include("stapel_geo.urls"))

which yields the canonical surface ``/geo/api/v1/...`` — the version
segment sits immediately after ``api/`` and there is no bare unversioned
path. The v1 patterns themselves live in ``urls_v1.py``; a future
breaking change mounts ``urls_v2.py`` alongside, never replaces in place.
"""
from django.urls import include, path

urlpatterns = [
    path("api/v1/", include("stapel_geo.urls_v1")),
]
