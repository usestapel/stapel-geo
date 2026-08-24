"""Serializer seam — re-exported from stapel-core, kept as an import path.

stapel-core 0.41.0 hoisted ``SerializerSeamMixin`` (and ``StapelAPIView``,
which is the mixin plus the two thin-view moves) into
``stapel_core.django.api.views``: twenty-four modules had each written the
same two attributes and two getters, which is a missing primitive, not a
pattern. This module now imports the canon rather than declaring a
twenty-fifth copy.

The name stays exported here because it is a documented extension point of
this library (MODULE.md) and host code subclasses against it. New code
should import ``StapelAPIView`` from stapel-core directly.
"""
from stapel_core.django.api.views import SerializerSeamMixin, StapelAPIView

__all__ = ["SerializerSeamMixin", "StapelAPIView"]
