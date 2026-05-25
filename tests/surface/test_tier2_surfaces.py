"""Tier 2 public surfaces snapshot — ``a2kit.<domain>``.

Tier 2 modules are the per-audience re-export facades (``a2kit.testing``,
``a2kit.ldd``) plus lazy submodule exports (``a2kit.schema``). Each
module gets its own expectation file at ``expected_tier_<domain>.txt``.
"""

from __future__ import annotations

import importlib
import types
from pathlib import Path

import pytest

from tests.surface._snapshot import assert_snapshot

#: Tier-2 module dotted name -> expectation file stem. Adding a Tier-2
#: module here requires also creating the matching expectation file,
#: which is the gate the snapshot suite enforces.
TIER2_MODULES: dict[str, str] = {
    "a2kit.testing": "expected_tier_testing.txt",
    "a2kit.ldd": "expected_tier_ldd.txt",
    "a2kit.schema": "expected_tier_schema.txt",
}


def _public_names(module: object) -> list[str]:
    """Public names of ``module``, excluding submodules attached by the
    import system. Same filter as Tier 1 so the test stays independent of
    test-session import order.
    """
    out: list[str] = []
    for n in dir(module):
        if n.startswith("_"):
            continue
        val = getattr(module, n)
        if isinstance(val, types.ModuleType) and val.__name__.startswith("a2kit."):
            continue
        out.append(n)
    return out


@pytest.mark.parametrize(
    ("dotted", "filename"),
    sorted(TIER2_MODULES.items()),
)
def test_tier2_surface_matches_snapshot(
    dotted: str,
    filename: str,
    regen_snapshots: bool,
) -> None:
    module = importlib.import_module(dotted)
    expected_path = Path(__file__).parent / filename
    assert_snapshot(
        dotted,
        _public_names(module),
        expected_path,
        regen=regen_snapshots,
    )
