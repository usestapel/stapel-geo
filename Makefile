# stapel-geo — contract emission + drift gate (contract-pipeline.md §2-3).
#
# This module emits its OWN contract triad (schema.json + flows.json + errors.json)
# per-module, from a single-module {geo + core} Django instance mounted at the
# canonical /geo/api/v1/ prefix (see _codegen.py / _codegen_settings.py /
# codegen_urls.py). PYTHON must have the module + its deps importable (the
# workspace venv, or a CI venv) and be a 3.12 interpreter (emission pin).
PYTHON ?= python3

.PHONY: contract contract-check

# Emit the contract triad into docs/.
contract:
	$(PYTHON) -m stapel_geo._codegen --out docs

# Drift gate: regenerate into a temp dir and diff against the committed docs/*.json.
contract-check:
	@tmp=$$(mktemp -d); \
	$(PYTHON) -m stapel_geo._codegen --out "$$tmp" || { rm -rf "$$tmp"; exit 1; }; \
	rc=0; \
	for f in schema.json flows.json errors.json; do \
		if ! cmp -s "docs/$$f" "$$tmp/$$f"; then \
			echo "DRIFT: docs/$$f is stale — run 'make contract' and commit it"; \
			diff "docs/$$f" "$$tmp/$$f" | head -20; rc=1; \
		fi; \
	done; \
	rm -rf "$$tmp"; \
	if [ $$rc -eq 0 ]; then echo "contract-check: docs/{schema,flows,errors}.json up to date"; fi; \
	exit $$rc


.PHONY: migration-lint

# Expand/contract gate for Django migrations (release-management.md §3;
# stapel_tools.migration_lint). Requires stapel-tools importable (the
# workspace venv, or `pip install stapel-tools` once published).
migration-lint:
	$(PYTHON) -m stapel_tools.migration_lint . --strict
