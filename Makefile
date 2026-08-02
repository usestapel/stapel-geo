# stapel-geo — contract emission + drift gate (contract-pipeline.md §2-3).
#
# This module emits its OWN contract triad (schema.json + flows.json + errors.json)
# per-module, from a single-module {geo + core} Django instance mounted at the
# canonical /geo/api/v1/ prefix (see _codegen.py / _codegen_settings.py /
# codegen_urls.py). PYTHON must have the module + its deps importable (the
# workspace venv, or a CI venv) and be a 3.12 interpreter (emission pin).
PYTHON ?= python3

.PHONY: contract contract-check

# Emit the contract triad + the human-readable error reference into docs/, plus
# the fifth artifact docs/llms.txt (stapel_tools.llms_txt — the module's own
# context slice for an agent; badge-canon §3). llms.txt is rendered from the
# freshly emitted triad PLUS docs/capabilities.json — the latter is HAND-AUTHORED
# in this module (no stapel_geo._capabilities emitter exists yet) and is only
# ever READ here, never written.
contract:
	$(PYTHON) -m stapel_geo._codegen --out docs
	$(PYTHON) -c "from stapel_geo._codegen import _configure; _configure(); \
	from django.core.management import call_command; \
	call_command('generate_error_docs', '--out', 'docs')"
	$(PYTHON) -m stapel_tools.llms_txt . --out docs

# Drift gate: regenerate into a temp dir and diff against the committed docs/*.json.
# capabilities.json is copied in verbatim (hand-authored, not regenerated) so
# llms_txt can render against it alongside the freshly regenerated triad.
contract-check:
	@tmp=$$(mktemp -d); \
	mkdir -p "$$tmp/docs"; \
	$(PYTHON) -m stapel_geo._codegen --out "$$tmp/docs" || { rm -rf "$$tmp"; exit 1; }; \
	cp docs/capabilities.json "$$tmp/docs/capabilities.json"; \
	$(PYTHON) -m stapel_tools.llms_txt "$$tmp" --out "$$tmp/docs" || { rm -rf "$$tmp"; exit 1; }; \
	rc=0; \
	for f in schema.json flows.json errors.json llms.txt; do \
		if ! cmp -s "docs/$$f" "$$tmp/docs/$$f"; then \
			echo "DRIFT: docs/$$f is stale — run 'make contract' and commit it"; \
			diff "docs/$$f" "$$tmp/docs/$$f" | head -20; rc=1; \
		fi; \
	done; \
	rm -rf "$$tmp"; \
	if [ $$rc -eq 0 ]; then echo "contract-check: docs/{schema,flows,errors,llms.txt} up to date"; fi; \
	exit $$rc


.PHONY: migration-lint

# Expand/contract gate for Django migrations (release-management.md §3;
# stapel_tools.migration_lint). Requires stapel-tools importable (the
# workspace venv, or `pip install stapel-tools` once published).
migration-lint:
	$(PYTHON) -m stapel_tools.migration_lint . --strict
