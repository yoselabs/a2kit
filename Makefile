.PHONY: test lint format check examples bootstrap typecheck coverage-diff a2kit-lint a2kit-check

bootstrap:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

a2kit-lint:
	uv run a2kit lint src/ tests/ examples/

a2kit-check:
	@echo "a2kit check requires --import path:server. Override per project."

typecheck:
	uv run ty check src/

typecheck-strict:
	uv run ty check --strict src/

coverage-diff:
	@uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=95 2>/dev/null || echo "⚠ no coverage.xml — run 'make test' first"

check: lint a2kit-lint typecheck test

examples:
	uv run python examples/multi_field_key_style.py
	uv run python examples/flat_key_style.py
	uv run python examples/tool_decorator.py
	uv run python examples/error_enricher.py
	uv run python examples/scaffold_cli.py --help
	uv run python examples/schema_snapshot.py
	uv run python examples/fat_tool.py
	uv run python examples/runner.py
	uv run python examples/formatter.py
	uv run python examples/feature_modules.py
	uv run python examples/streaming_tool.py
	uv run python examples/cassette_test.py
	uv run python examples/v03_minimal_mcp.py
	uv run python examples/feature_class.py
	uv run python examples/key_namedtuple.py
	uv run python examples/router_class.py
	uv run python examples/select_grammar.py
	uv run python examples/typed_decorator.py
	uv run python examples/projection.py
	uv run python examples/cel_filter_tool.py
	uv run python examples/toml_capabilities.py
	uv run python examples/v05_minimal_mcp.py
	uv run python examples/typed_key_literal.py
