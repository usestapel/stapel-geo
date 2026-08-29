# stapel-geo — contract emission + drift gate (contract-pipeline.md §2-3).
#
# This module emits its OWN contract triad (schema.json + flows.json + errors.json)
# per-module, from a single-module {geo + core} Django instance mounted at the
# canonical /geo/api/v1/ prefix (see _codegen.py / _codegen_settings.py /
# codegen_urls.py). PYTHON must have the module + its deps importable (the
# workspace venv, or a CI venv) and be a 3.12 interpreter (emission pin).
PYTHON ?= python3

# llms.txt ceiling. RAISED DELIBERATELY from the 4000 default in 0.4.1, which is
# the escape the tool itself names — and it is a raise, not a silencing: the file
# is still refused whole if it goes over, because a truncated context file reads
# exactly like a complete one. What paid for it is a subsystem, not prose: the
# ipgeo seam (locator registry, the proxy-trust resolver, the fallback centre)
# added an axis, two extension points and three surface entries, and the honest
# choice was between describing them and pretending geo has one fewer moving
# part than it has.
LLMS_BUDGET ?= 4600

.PHONY: contract contract-check

# Emit the contract triad + the human-readable error reference into docs/, plus
# patch the `surface` section into docs/capabilities.json (stapel_tools.surface
# --patch — the symbols a product is meant to CALL, discoverability-design.md
# §1.2; derived by AST from docs/capabilities.meta.json's surface_roots, a
# selected export with no curated intent fails naming it), plus the fifth
# artifact docs/llms.txt (stapel_tools.llms_txt — the module's own context
# slice for an agent; badge-canon §3), rendered from the freshly emitted triad
# PLUS the patched capabilities.json. The REST of capabilities.json (provides/
# axes/extension_points/operations_total) is still HAND-AUTHORED in this module
# (no stapel_geo._capabilities emitter exists yet) — `--patch` touches only
# module/version and `surface`, leaving everything else byte-for-byte.
# README.md is the SIXTH artifact (tracker #257): assembled by
# stapel_tools.readme from docs/readme.md (the human half — what this module
# is, how to think about it) plus everything emitted above. Badges, version,
# surface counts and doc links are generated, so a release cannot leave them
# behind. Edit docs/readme.md; never README.md.
contract:
	$(PYTHON) -m stapel_geo._codegen --out docs
	$(PYTHON) -c "from stapel_geo._codegen import _configure; _configure(); \
	from django.core.management import call_command; \
	call_command('generate_error_docs', '--out', 'docs')"
	$(PYTHON) -m stapel_tools.surface . --patch
	$(PYTHON) -m stapel_tools.llms_txt . --out docs --budget $(LLMS_BUDGET)
	$(PYTHON) -m stapel_tools.readme .

# Drift gate. `stapel_tools.surface . --patch --check` runs against the real
# repo (it AST-scans the actual source files named by surface_roots, so it
# cannot run against a docs/-only temp dir) and compares the freshly patched
# capabilities.json to the committed one in memory, byte for byte. The triad
# (schema/flows/errors) + llms.txt still regenerate into a temp dir and diff
# there, as before; llms.txt is rendered against the (already checked)
# committed capabilities.json, copied in verbatim for that render.
contract-check:
	@$(PYTHON) -m stapel_tools.surface . --patch --check || exit 1; \
	tmp=$$(mktemp -d); \
	mkdir -p "$$tmp/docs"; \
	$(PYTHON) -m stapel_geo._codegen --out "$$tmp/docs" || { rm -rf "$$tmp"; exit 1; }; \
	cp docs/capabilities.json "$$tmp/docs/capabilities.json"; \
	$(PYTHON) -m stapel_tools.llms_txt "$$tmp" --out "$$tmp/docs" --budget $(LLMS_BUDGET) || { rm -rf "$$tmp"; exit 1; }; \
	rc=0; \
	for f in schema.json flows.json errors.json llms.txt; do \
		if ! cmp -s "docs/$$f" "$$tmp/docs/$$f"; then \
			echo "DRIFT: docs/$$f is stale — run 'make contract' and commit it"; \
			diff "docs/$$f" "$$tmp/docs/$$f" | head -20; rc=1; \
		fi; \
	done; \
	rm -rf "$$tmp"; \
	$(PYTHON) -m stapel_tools.readme . --check || rc=1; \
	if [ $$rc -eq 0 ]; then echo "contract-check: docs/{capabilities,schema,flows,errors,llms.txt} + README.md up to date"; fi; \
	exit $$rc


.PHONY: migration-lint

# Expand/contract gate for Django migrations (release-management.md §3;
# stapel_tools.migration_lint). Requires stapel-tools importable (the
# workspace venv, or `pip install stapel-tools` once published).
migration-lint:
	$(PYTHON) -m stapel_tools.migration_lint . --strict
