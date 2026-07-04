"""geo.import.completed emit contract (schema-validated in-process)."""
import pytest
from stapel_core.comm.exceptions import SchemaValidationError

from stapel_geo.actions import GEO_IMPORT_COMPLETED, emit_import_completed

_GOOD = {
    "geofile_id": 1,
    "location_level": 0,
    "feature_count": 3,
    "status": "completed",
}


class TestEmitContract:
    def test_valid_payload_emits(self):
        event = emit_import_completed(dict(_GOOD))
        assert event.event_type == GEO_IMPORT_COMPLETED

    def test_missing_required_field_rejected(self):
        with pytest.raises(SchemaValidationError):
            emit_import_completed({"geofile_id": 1})

    def test_status_must_be_completed(self):
        payload = dict(_GOOD, status="failed")
        with pytest.raises(SchemaValidationError):
            emit_import_completed(payload)

    def test_extra_key_rejected(self):
        payload = dict(_GOOD, unexpected=True)
        with pytest.raises(SchemaValidationError):
            emit_import_completed(payload)
