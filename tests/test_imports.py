"""GADM import status machine — GDAL-free, with a fake GeoFile and mock importer."""
import io

import pytest

from stapel_geo.imports import (
    GeoFileImporter,
    ImportStatus,
    ImportValidationError,
    parse_geojson,
)
from stapel_geo.tests.fakes import FakeGeoFile


def _collection(level=2, n=3):
    return {
        "name": f"gadm41_TST_{level}",
        "type": "FeatureCollection",
        "features": [{"properties": {"GID_%d" % level: f"TST.{i}"}} for i in range(n)],
    }


class TestParseGeojson:
    def test_reads_level_and_features(self):
        level, features = parse_geojson(io.BytesIO(_json(_collection(level=2, n=3))))
        assert level == 2
        assert len(features) == 3

    def test_missing_level_suffix_rejected(self):
        bad = {"name": "gadm41_TST", "type": "FeatureCollection", "features": []}
        with pytest.raises(ImportValidationError):
            parse_geojson(io.BytesIO(_json(bad)))

    def test_non_featurecollection_rejected(self):
        bad = {"name": "gadm41_TST_0", "type": "Feature", "features": []}
        with pytest.raises(ImportValidationError):
            parse_geojson(io.BytesIO(_json(bad)))

    def test_non_json_rejected(self):
        with pytest.raises(ImportValidationError):
            parse_geojson(io.BytesIO(b"not json at all"))

    def test_error_carries_key(self):
        try:
            parse_geojson(io.BytesIO(b"{"))
        except ImportValidationError as exc:
            assert exc.error_key == "error.400.invalid_geojson"
        else:
            raise AssertionError("expected ImportValidationError")


class TestImportHappyPath:
    def test_completes_and_transitions(self):
        gf = FakeGeoFile(_collection(level=1, n=3))
        imported = []
        events = []
        status = GeoFileImporter(
            gf,
            feature_importer=lambda level, feat: imported.append((level, feat)),
            emit=events.append,
            batch_size=2,
        ).run()

        assert status == ImportStatus.COMPLETED
        assert gf.import_status == ImportStatus.COMPLETED
        assert gf.validation_result == "OK"
        assert gf.location_level == 1
        assert gf.import_total == 3
        assert gf.import_progress == 3
        assert len(imported) == 3
        # first transition flips to PROCESSING
        assert gf.saved_fields[0] == ["import_status"]

    def test_emits_completed_once_with_payload(self):
        gf = FakeGeoFile(_collection(level=0, n=2), file_id=42)
        events = []
        GeoFileImporter(
            gf, feature_importer=lambda level, feat: None, emit=events.append
        ).run()
        assert events == [
            {
                "geofile_id": 42,
                "location_level": 0,
                "feature_count": 2,
                "status": "completed",
            }
        ]

    def test_progress_batched(self):
        gf = FakeGeoFile(_collection(level=1, n=5))
        GeoFileImporter(
            gf, feature_importer=lambda level, feat: None, batch_size=2
        ).run()
        # progress flushes at 2, 4, 5
        progress_saves = [f for f in gf.saved_fields if f == ["import_progress"]]
        assert len(progress_saves) == 3


class TestImportFailurePaths:
    def test_invalid_geojson_marks_failed_and_no_emit(self):
        gf = FakeGeoFile({"name": "bad", "type": "Nope", "features": []})
        events = []
        status = GeoFileImporter(
            gf, feature_importer=lambda level, feat: None, emit=events.append
        ).run()
        assert status == ImportStatus.FAILED
        assert gf.import_status == ImportStatus.FAILED
        assert gf.import_error
        assert events == []

    def test_feature_importer_error_marks_failed(self):
        gf = FakeGeoFile(_collection(level=1, n=3))

        def boom(level, feat):
            raise ValueError("bad geometry")

        events = []
        status = GeoFileImporter(gf, feature_importer=boom, emit=events.append).run()
        assert status == ImportStatus.FAILED
        assert "bad geometry" in gf.import_error
        assert events == []


def _json(obj):
    import json

    return json.dumps(obj).encode("utf-8")
