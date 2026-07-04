"""comm Action surface of stapel-geo.

``geo.import.completed`` is emitted once a GADM GeoFile finishes importing
(the async path). It is a public fact — consumers (search reindexers,
caches) subscribe by name. The schema in ``schemas/emits/`` is registered
here so ``emit`` validates the payload even before any subscriber exists.

This module imports no GDAL; it is loaded from ``apps.py:ready()``.
"""
import json
from pathlib import Path

from stapel_core.comm import emit
from stapel_core.comm.registry import action_registry

GEO_IMPORT_COMPLETED = "geo.import.completed"

_SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas" / "emits"


def _schema(name: str) -> dict:
    return json.loads((_SCHEMAS_DIR / f"{name}.json").read_text(encoding="utf-8"))


# Register the emit contract so VALIDATE_SCHEMAS enforces it even with no
# subscriber present (a schema without a subscriber is still validated).
action_registry.register_schema(GEO_IMPORT_COMPLETED, _schema(GEO_IMPORT_COMPLETED))


def emit_import_completed(payload: dict):
    """Emit ``geo.import.completed`` (through the transactional outbox)."""
    return emit(GEO_IMPORT_COMPLETED, payload)


__all__ = ["GEO_IMPORT_COMPLETED", "emit_import_completed"]
