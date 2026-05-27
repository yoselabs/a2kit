.PHONY: test lint format check examples example-smoke bootstrap typecheck coverage-diff a2kit-lint a2kit-check mutate mutate-fast mutate-show mutate-html mutate-baseline adr-index adr-check component-map markdown-lint eval eval-smoke surface-snapshot opa-check actionlint-check

# OPA (Open Policy Agent) version pin — `make opa-check` enforces this
# at lint time so the policy bundle is evaluated against a known engine.
# Bump deliberately; document why in the ADR for the change.
OPA_VERSION := 1.16.2

# actionlint version pin — `make actionlint-check` enforces this so
# workflow validation runs against a known parser. Same rationale as OPA.
ACTIONLINT_VERSION := 1.7.12

bootstrap:
	uv sync --all-extras --dev
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type pre-push
	@$(MAKE) opa-check || { \
		echo ""; \
		echo "OPA $(OPA_VERSION) is required for 'make lint' (rego policies)."; \
		echo "Install: brew install opa  (macOS)"; \
		echo "         curl -L -o /usr/local/bin/opa https://openpolicyagent.org/downloads/v$(OPA_VERSION)/opa_linux_amd64_static && chmod +x /usr/local/bin/opa  (Linux)"; \
		echo ""; \
		exit 1; \
	}
	@$(MAKE) actionlint-check || { \
		echo ""; \
		echo "actionlint $(ACTIONLINT_VERSION) is required for 'make lint' (.github/workflows/*.yml)."; \
		echo "Install: brew install actionlint  (macOS)"; \
		echo "         bash <(curl -L https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash) $(ACTIONLINT_VERSION) /usr/local/bin  (Linux)"; \
		echo ""; \
		exit 1; \
	}

# Verify OPA is installed and matches OPA_VERSION. Soft on minor drift?
# No — pinned exactly so policy semantics are reproducible.
opa-check:
	@command -v opa >/dev/null 2>&1 || { echo "ERROR: opa not on PATH"; exit 1; }
	@INSTALLED=$$(opa version | awk '/^Version:/ {print $$2}'); \
	if [ "$$INSTALLED" != "$(OPA_VERSION)" ]; then \
		echo "ERROR: OPA version mismatch — pinned $(OPA_VERSION), installed $$INSTALLED"; \
		echo "Bump OPA_VERSION in Makefile after intentional upgrade (update ADR + re-validate policies)."; \
		exit 1; \
	fi

# Verify actionlint is installed and matches ACTIONLINT_VERSION. Same
# reproducibility argument as OPA: workflow validation depends on the
# parser version.
actionlint-check:
	@command -v actionlint >/dev/null 2>&1 || { echo "ERROR: actionlint not on PATH"; exit 1; }
	@INSTALLED=$$(actionlint -version | head -n1); \
	if [ "$$INSTALLED" != "$(ACTIONLINT_VERSION)" ]; then \
		echo "ERROR: actionlint version mismatch — pinned $(ACTIONLINT_VERSION), installed $$INSTALLED"; \
		echo "Bump ACTIONLINT_VERSION in Makefile after intentional upgrade (update ADR + re-validate policies)."; \
		exit 1; \
	fi

test:
	uv run pytest

example-smoke:
	WORKSPACE_ROOT=$${WORKSPACE_ROOT:-/tmp/a2kit-example-smoke} uv run pytest examples/mcp_google_auth/tests/ --no-cov -q

surface-snapshot:
	uv run pytest tests/surface --regen-snapshots --no-cov -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check src/
	uv run ty check tests/
	uv run ty check examples/
	uv run a2kit lint static src/ tests/ examples/
	@$(MAKE) actionlint-check
	actionlint
	@$(MAKE) opa-check
	uv run a2kit lint rego src/
	uv run pytest tests/test_readme_symbol_drift.py --no-cov -q
	uv run pytest tests/test_spec_symbol_drift.py --no-cov -q

format:
	uv run ruff format .
	uv run ruff check --fix .

a2kit-lint:
	uv run a2kit lint static src/ tests/ examples/

a2kit-check:
	@echo "a2kit lint runtime requires --import path:server. Override per project."

typecheck:
	uv run ty check src/
	uv run ty check tests/

typecheck-strict:
	uv run ty check --strict src/

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95 2>/dev/null || echo "⚠ no coverage.xml — run 'make test' first"

check: lint test

examples:
	uv run python -m examples.tracker.server --help
	uv run python -m examples.streaming_logger.server --help

# Mutation testing — see docs/MUTATION_BASELINE.md for the latest score.
mutate:
	uv run mutmut run

mutate-fast:
	@CHANGED=$$(git diff --name-only origin/main... -- 'src/a2kit/*.py' | tr '\n' ' '); \
	if [ -z "$$CHANGED" ]; then \
		echo "no a2kit source files changed since origin/main; nothing to mutate"; \
	else \
		echo "mutating: $$CHANGED"; \
		uv run mutmut run $$CHANGED; \
	fi

mutate-show:
	uv run mutmut results

mutate-html:
	uv run mutmut browse

mutate-baseline:
	uv run mutmut run
	uv run mutmut results > .mutmut-baseline.txt
	@echo "baseline written to .mutmut-baseline.txt"

# ADR index — regenerates docs/adr/INDEX.md from frontmatter. Run on
# every ADR change; pre-commit enforces --check mode so the on-disk
# INDEX never drifts.
adr-index:
	uv run python scripts/adr_index.py

adr-check:
	uv run python scripts/adr_index.py --check

# Component map — regenerates docs/COMPONENT_MAP.md from the layer
# manifest + import graph. Pre-commit enforces --check mode so the
# on-disk map never drifts.
component-map:
	uv run python scripts/component_map.py

# Code-mode correctness eval — drives real models (haiku + sonnet) via the
# `claude` CLI through the real `execute` tool. NOT part of `make check`: it
# costs tokens and needs the `claude` CLI. `eval-smoke` checks the harness
# (server build + get_schema + execute round-trip) without spending tokens.
eval:
	uv run python evals/codemode_correctness.py

eval-smoke:
	uv run python evals/codemode_correctness.py --smoke

# Markdown lint — runs pymarkdownlnt across docs/, CHANGELOG.md, README.md.
# Config in .pymarkdown.json. Use `uv run pymarkdown --config .pymarkdown.json
# fix <path>` to auto-fix structural issues (blank lines, list markers, etc.).
markdown-lint:
	uv run pymarkdown --config .pymarkdown.json scan docs/ CHANGELOG.md README.md
