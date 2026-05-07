.PHONY: test lint format check examples bootstrap

bootstrap:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

check: lint test

examples:
	uv run python examples/a2db_style.py
	uv run python examples/a2atlassian_style.py
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
