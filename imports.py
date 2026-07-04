"""GADM import status machine — GDAL-free orchestration.

The heavy lifting (building geometries, upserting ``Location`` rows) is a
``feature_importer`` callable injected by the caller; the model wires in the
GDAL-backed one from ``stapel_geo.models``. Everything in this module —
GeoJSON validation, the pending -> processing -> completed/failed state
transitions, progress accounting, the completion event — runs without GDAL,
so the status machine is fully unit-testable with a fake GeoFile and a mock
feature importer.

``ImportStatus`` uses ``django.db.models.TextChoices`` (plain Django, not
GeoDjango) so the model and this module share one source of truth.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional, Protocol

from django.db import models

logger = logging.getLogger(__name__)


class ImportStatus(models.TextChoices):
    """Lifecycle of a GeoFile import."""

    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ImportValidationError(Exception):
    """The GeoJSON payload is not a usable GADM extract.

    Carries ``error.400.invalid_geojson`` so HTTP callers surface a stable
    key. Imported lazily to keep this module light; set in ``__init__``.
    """

    def __init__(self, message: str):
        from .errors import ERR_400_INVALID_GEOJSON

        self.error_key = ERR_400_INVALID_GEOJSON
        super().__init__(message)


def parse_geojson(fileobj) -> tuple[int, list[dict]]:
    """Validate a GADM GeoJSON file-like and return ``(level, features)``.

    The GADM depth level is taken from the collection ``name`` suffix
    (``gadm41_LUX_2`` -> level 2). Raises :class:`ImportValidationError`
    for anything that is not a level-tagged ``FeatureCollection``. Pure —
    no GDAL, no geometry parsing (that happens per-feature downstream).
    """
    fileobj.seek(0)
    try:
        data = json.load(fileobj)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ImportValidationError("Not a JSON file") from None

    name = data.get("name")
    if not name or not re.match(r".*_\d+$", name):
        raise ImportValidationError(
            "GeoJSON 'name' should end with a depth level (e.g. gadm41_LUX_2)"
        )
    try:
        level = int(name.rsplit("_", 1)[-1])
    except ValueError:
        raise ImportValidationError(f"Cannot read depth level from name: {name}") from None

    if data.get("type") != "FeatureCollection":
        raise ImportValidationError("GeoJSON should be a FeatureCollection")

    features = data.get("features")
    if not isinstance(features, list):
        raise ImportValidationError("GeoJSON 'features' should be a list")

    return level, features


class _GeoFileLike(Protocol):
    id: object
    import_status: str
    import_progress: int
    import_total: int
    import_error: str
    location_level: int
    validation_result: str

    def open_geojson(self): ...
    def save(self, *args, **kwargs): ...


class GeoFileImporter:
    """Drive one GeoFile import through its status transitions.

    Parameters:
        geofile: any object exposing the GeoFile import fields, ``save`` and
            ``open_geojson()`` (the real model, or a test double).
        feature_importer: ``callable(level, feature)`` performing the
            geometry/Location upsert (GDAL). Injected so the machine stays
            GDAL-free.
        emit: optional ``callable(payload: dict)`` invoked once on success
            with the ``geo.import.completed`` payload.
        batch_size: how often progress is flushed to the store.
    """

    def __init__(
        self,
        geofile: _GeoFileLike,
        *,
        feature_importer: Callable[[int, dict], None],
        emit: Optional[Callable[[dict], None]] = None,
        batch_size: int = 10,
    ):
        self.geofile = geofile
        self.feature_importer = feature_importer
        self.emit = emit
        self.batch_size = batch_size

    def run(self) -> str:
        """Execute the import; returns the terminal status. Never raises —
        failures are recorded on the GeoFile (matching the async path)."""
        gf = self.geofile
        try:
            gf.import_status = ImportStatus.PROCESSING
            gf.save(update_fields=["import_status"])

            level, features = parse_geojson(gf.open_geojson())
            gf.location_level = level
            gf.import_total = len(features)
            gf.import_progress = 0
            gf.save(update_fields=["location_level", "import_total", "import_progress"])

            self._import_features(level, features)

            gf.import_status = ImportStatus.COMPLETED
            gf.validation_result = "OK"
            gf.save(update_fields=["import_status", "validation_result"])
            logger.info("GeoFile %s import completed: %d features", gf.id, len(features))
            self._emit_completed(level, len(features))
            return ImportStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001 — errors are stored, not raised
            gf.import_status = ImportStatus.FAILED
            gf.import_error = str(exc)
            gf.validation_result = str(exc)
            gf.save(update_fields=["import_status", "import_error", "validation_result"])
            logger.error("GeoFile %s import failed: %s", getattr(gf, "id", "?"), exc)
            return ImportStatus.FAILED

    def _import_features(self, level: int, features: list[dict]) -> None:
        gf = self.geofile
        total = len(features)
        for i, feature in enumerate(features):
            self.feature_importer(level, feature)
            done = i + 1
            if done % self.batch_size == 0 or done == total:
                gf.import_progress = done
                gf.save(update_fields=["import_progress"])

    def _emit_completed(self, level: int, feature_count: int) -> None:
        if self.emit is None:
            return
        self.emit(
            {
                "geofile_id": self.geofile.id,
                "location_level": level,
                "feature_count": feature_count,
                "status": ImportStatus.COMPLETED.value,
            }
        )


__all__ = [
    "ImportStatus",
    "ImportValidationError",
    "parse_geojson",
    "GeoFileImporter",
]
