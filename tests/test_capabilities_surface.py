"""Drift gate for the `surface` section of ``docs/capabilities.json``.

The IsNotAnonymousUser incident is why this section exists at all: a product
hand-rolled its own DRF write-gate, not knowing stapel-core already shipped
one — a hole in production, fixed by hand. stapel-geo's own equivalent risk:
a product re-deriving geohash neighbour-widening / haversine math, or calling
a geocoder provider directly and losing the spend ledger, because nothing in
the module's contract could even name ``geohash.nearby``/``geocoding.service.
geocode`` (``axes`` describes what you switch on, ``extension_points`` what
you replace — neither answers "is there already a function for this").

``surface`` names them, with one curated line each saying when to reach for
them. The entry set is derived by AST from the roots in
``docs/capabilities.meta.json`` — a new public function in one of the
declared root files shows up here by itself and fails emission until
somebody explains it.

Honest boundary: the REST of this module's ``capabilities.json`` (provides/
axes/extension_points/operations_total) is still hand-written — this module
DOES emit its own schema/flows/errors triad (``stapel_geo._codegen``), but no
``stapel_geo._capabilities`` emitter exists yet for the document itself — so
only ``module``/``version``/``surface`` are gated below.
"""
import json
from pathlib import Path

import pytest

try:
    import stapel_tools  # noqa: F401  (probe: the emitter must be importable)
except ImportError as exc:  # pragma: no cover - environment failure, not a branch
    # NOT pytest.importorskip. A drift gate that skips when its emitter is
    # missing reports `1 skipped`, exits 0, and disappears among a hundred
    # green tests — exactly how a surface entry could go unexplained with
    # nothing red anywhere to say so. A gate that cannot run has FAILED; it
    # has not passed.
    raise RuntimeError(
        "capabilities surface drift gate cannot run: stapel-tools is not "
        "importable, and it carries the capabilities emitter this gate "
        "measures drift against. Install it (workspace venv, or `pip install "
        "stapel-tools`) and re-run. This is a hard failure on purpose — a "
        "skipped drift gate is silently no gate."
    ) from exc

from stapel_tools.surface import _stable_json, load_meta, patch_capabilities  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
COMMITTED = REPO / "docs" / "capabilities.json"

# One root file each. Kept in sync with docs/capabilities.meta.json's
# surface_roots — see test_a_new_public_function_cannot_slip_in_unexplained.
SURFACE_ROOT_FILES = (
    "geohash.py",
    "services.py",
    "geocoding/service.py",
    "geocoding/providers.py",
    "search/__init__.py",
)

SURFACE_ENTRIES = {
    "encode",
    "distance_km",
    "rank_by_proximity",
    "nearby",
    "nearby_by_coords",
    "nearby_by_geohash",
    "nearby_rows_by_coords",
    "nearby_rows_by_geohash",
    "radius",
    "bbox",
    "resolve",
    "get_geocoder",
    "geocode",
    "register_geocoder",
    "registered_geocoders",
    "get_backend",
}


def _emitted() -> dict:
    try:
        return patch_capabilities(REPO, load_meta(REPO))
    except SystemExit as exc:  # the LOUD rule — report it, don't bury it
        pytest.fail(f"capabilities emission refused: {exc}", pytrace=False)


def test_no_drift():
    assert COMMITTED.read_text() == _stable_json(_emitted()), (
        "docs/capabilities.json is stale — run `make contract` and commit it"
    )


def test_version_tracks_pyproject():
    """The document carries the module version — a hand-written copy of a
    version number is exactly the drift this section exists to stop."""
    import tomllib

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert json.loads(COMMITTED.read_text())["version"] == (
        pyproject["project"]["version"]
    )


def test_every_surface_entry_is_named_and_explained():
    surface = json.loads(COMMITTED.read_text())["surface"]
    by_name = {e["name"]: e for e in surface}
    assert SURFACE_ENTRIES <= set(by_name)
    for name in SURFACE_ENTRIES:
        entry = by_name[name]
        assert entry["kind"] in ("gate_function", "predicate", "factory"), entry
        assert entry["intent"].strip(), entry


def test_a_new_public_function_cannot_slip_in_unexplained():
    """The set is derived, so the gate is not "did somebody remember to list
    it" but "does every public function in the declared roots have a line"."""
    from stapel_tools.surface import scan_functions

    declared = {e["name"] for e in json.loads(COMMITTED.read_text())["surface"]}
    for module in SURFACE_ROOT_FILES:
        assert set(scan_functions(REPO / module)) <= declared
