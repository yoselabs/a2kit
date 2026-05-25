"""Pytest plumbing for tier-surface snapshot tests.

Adds the ``--regen-snapshots`` flag that switches the suite from
assertion mode to write-mode. In write-mode each test (re)writes its
expectation file to match the observed value instead of raising on
drift. Run as ``pytest tests/surface --regen-snapshots`` to seed or
update the expectation files.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--regen-snapshots",
        action="store_true",
        default=False,
        help=("Rewrite tests/surface/expected_*.txt expectation files to match the currently-observed public surfaces."),
    )


@pytest.fixture
def regen_snapshots(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--regen-snapshots"))
