.PHONY: test lint format check examples bootstrap typecheck coverage-diff a2kit-lint a2kit-check mutate mutate-fast mutate-show mutate-html mutate-baseline

bootstrap:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check src/
	uv run ty check tests/
	uv run ty check examples/
	uv run a2kit lint static src/ tests/ examples/
	uv run pytest tests/test_readme_symbol_drift.py --no-cov -q

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
