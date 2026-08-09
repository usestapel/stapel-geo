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


# --- README.md — the sixth artifact (tracker #257) ---------------------------
#
# README.md is assembled by ``stapel_tools.readme`` from docs/readme.md (the
# human half: what this module is and how to think about it) plus the contract
# documents above (badges, version, surface counts, doc links, the flow index).
# stapel-geo is one of only two modules in the fleet with a non-empty
# docs/flows.json — the "Flows" doc link renders from docs/flows/en/README.md,
# generated once via ``generate_project_docs --languages en`` (see git log).
# Unlike stapel-auth there is no bilingual (ru) tree and no dedicated
# regenerate-and-diff test for that tree yet — same documented gap as the
# schema/flows/errors triad above (out of scope here).

def test_readme_is_assembled_and_has_no_drift():
    from stapel_tools.readme import load_inputs, render, static_languages

    inputs = load_inputs(REPO)
    languages = static_languages(REPO)
    assert languages == ["en"], "expected exactly the English static body docs/readme.md"
    committed = (REPO / "README.md").read_text()
    assert committed == render(REPO, inputs, "en", languages), (
        "README.md drifted — run `make contract` and commit README.md "
        "(edit prose in docs/readme.md, never README.md itself)"
    )


def test_readme_version_matches_the_package():
    """The #226 gate, at the point where the number is published."""
    import tomllib

    from stapel_tools.readme import load_inputs, resolve_version

    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert resolve_version(load_inputs(REPO)) == pyproject["project"]["version"]


def test_readme_links_the_flow_index():
    """The non-empty flows.json (one of two in the fleet) must produce a live link."""
    readme = (REPO / "README.md").read_text()
    assert "docs/flows/en/README.md" in readme
