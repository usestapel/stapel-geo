"""docs/llms.txt drift gate — the fifth contract artifact (badge-canon §3).

Scope note: unlike stapel-auth/stapel-notifications/stapel-profiles, this
module has no ``stapel_geo._capabilities`` emitter yet — ``docs/capabilities.json``
here is HAND-AUTHORED (see the Makefile `contract` comment) and this module
has no pre-existing pytest-level drift gate for its schema/flows/errors triad
either (only the Makefile `contract-check` diff loop covers it). Fixing that
gap is out of scope here; this test file adds ONLY the llms.txt gate, which
renders from the committed (hand-authored) capabilities.json plus the
committed triad — no Django, no subprocess, no regeneration of anything.

Regenerate after any change to docs/{schema,flows,errors,capabilities}.json:

    make contract        # or: python -m stapel_tools.llms_txt . --out docs

then commit ``docs/llms.txt``. Without regenerating, the drift gate below
fails.
"""
import json
from pathlib import Path

from stapel_tools.llms_txt import render

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"


def _inputs() -> dict:
    data = {"capabilities": json.loads((DOCS / "capabilities.json").read_text())}
    for key, name in (
        ("schema", "schema.json"),
        ("errors", "errors.json"),
        ("flows", "flows.json"),
    ):
        path = DOCS / name
        data[key] = json.loads(path.read_text()) if path.is_file() else None
    return data


def test_llms_txt_committed():
    assert (DOCS / "llms.txt").is_file(), "missing docs/llms.txt — run `make contract`"


def test_llms_txt_has_no_drift():
    """Re-render in-process from the committed inputs; must match byte-for-byte."""
    committed = (DOCS / "llms.txt").read_text()
    regenerated = render(_inputs())
    assert committed == regenerated, (
        "docs/llms.txt drifted — run `make contract` and commit docs/llms.txt"
    )


def test_llms_txt_emission_is_deterministic():
    """Two independent emissions from the same inputs are byte-identical."""
    inputs = _inputs()
    assert render(inputs) == render(inputs)
