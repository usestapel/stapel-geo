"""Shared, GDAL-free view seam mixin (used by both spatial and geocoder views)."""


class SerializerSeamMixin:
    """Overridable serializer seam for every stapel-geo APIView.

    Host projects can swap the request/response serializer of any view by
    subclassing and setting ``request_serializer_class`` /
    ``response_serializer_class`` (or overriding the getters for
    per-request decisions) — no need to rewrite the HTTP method bodies.
    """

    request_serializer_class = None
    response_serializer_class = None

    def get_request_serializer_class(self):
        return self.request_serializer_class

    def get_response_serializer_class(self):
        return self.response_serializer_class


__all__ = ["SerializerSeamMixin"]
