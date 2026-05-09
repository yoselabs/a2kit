.PHONY: test lint format check examples bootstrap typecheck coverage-diff a2kit-lint a2kit-check

bootstrap:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check src/
	uv run a2kit lint static src/ tests/ examples/

format:
	uv run ruff format .
	uv run ruff check --fix .

a2kit-lint:
	uv run a2kit lint static src/ tests/ examples/

a2kit-check:
	@echo "a2kit lint runtime requires --import path:server. Override per project."

typecheck:
	uv run ty check src/

typecheck-strict:
	uv run ty check --strict src/

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95 2>/dev/null || echo "⚠ no coverage.xml — run 'make test' first"

check: lint test

examples:
	uv run python -m examples.tracker.server --help
	uv run python -m examples.streaming_logger.server --help
