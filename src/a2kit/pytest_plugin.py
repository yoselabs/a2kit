"""Pytest plugin — registers `--update-schema-snapshots` and the `schema_snapshot` fixture.

Picked the explicit-opt-in approach (the user's `conftest.py` does
`pytest_plugins = ["a2kit.pytest_plugin"]`, or pytest is invoked with
`-p a2kit.pytest_plugin`) over auto-registration via setuptools entry points.

Why: auto-registration as `pytest11` causes pytest to import this module before
it starts coverage. Importing `a2kit.pytest_plugin` triggers `a2kit/__init__.py`,
which eagerly imports the rest of the package — and since coverage hasn't
started yet, those import-time lines (class definitions, module-level constants)
are never recorded. Result: every consuming repo loses 100% coverage on
`a2kit/*`. Explicit `-p` registration loads the plugin AFTER coverage starts.

Cost of opt-in: one line in the consumer's `conftest.py`. Cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the `--update-schema-snapshots` and `--update-cassettes` flags."""
    parser.addoption(
        "--update-schema-snapshots",
        action="store_true",
        default=False,
        help="Write/overwrite a2kit schema snapshots instead of asserting against them.",
    )
    parser.addoption(
        "--update-cassettes",
        action="store_true",
        default=False,
        help="Re-record HTTP cassettes (a2kit.testing.cassette) instead of replaying them.",
    )


@pytest.fixture
def update_cassettes(request: pytest.FixtureRequest) -> bool:
    """Boolean fixture indicating whether `--update-cassettes` was passed.

    Tests that want to switch a cassette into "all" record mode can read this
    and forward it to `a2kit.testing.cassette(..., record_mode="all" if update else None)`.
    """
    return bool(request.config.getoption("--update-cassettes"))


@pytest.fixture
def schema_snapshot(request: pytest.FixtureRequest) -> Any:
    """Fixture: returns a callable `(server, snapshot_dir) -> None`.

    On `--update-schema-snapshots`, writes snapshots. Otherwise asserts.

    The implementation imports `a2kit.testing` lazily so loading this plugin
    via entry-points does not eagerly import the rest of the package — that
    would defeat coverage measurement on the consuming repo.
    """
    update = bool(request.config.getoption("--update-schema-snapshots"))

    def _check(server: FastMCP, snapshot_dir: Path) -> None:
        from a2kit.testing import assert_schemas_match, snapshot_schemas  # noqa: PLC0415

        if update or not snapshot_dir.exists() or not any(snapshot_dir.glob("*.json")):
            snapshot_schemas(server, snapshot_dir)
            return
        assert_schemas_match(server, snapshot_dir)

    return _check


__all__ = ["pytest_addoption", "schema_snapshot", "update_cassettes"]
