"""Tier 1 public surface snapshot — ``a2kit.*``.

Tier 1 is the 95% verb-authoring surface (ADR 0004). The observed
surface is ``dir(a2kit)`` filtered to names that do not start with an
underscore and excluding submodules attached by Python's import system
(e.g. ``a2kit.app``, ``a2kit.config``) unless they appear in
``_LAZY_MODULES`` as intentional Tier-2 module exports. This makes the
test independent of import order in the test session.
"""

from __future__ import annotations

import types
from pathlib import Path

import a2kit

from tests.surface._snapshot import assert_snapshot

_EXPECTED_PATH = Path(__file__).parent / "expected_tier1.txt"


def _public_names() -> list[str]:
    intended_modules: set[str] = set(a2kit._LAZY_MODULES.keys())  # type: ignore[attr-defined]
    out: list[str] = []
    for n in dir(a2kit):
        if n.startswith("_"):
            continue
        val = getattr(a2kit, n)
        if isinstance(val, types.ModuleType) and val.__name__.startswith("a2kit."):
            if n in intended_modules:
                out.append(n)
            continue
        out.append(n)
    return out


def test_tier1_surface_matches_snapshot(regen_snapshots: bool) -> None:
    assert_snapshot(
        "a2kit",
        _public_names(),
        _EXPECTED_PATH,
        regen=regen_snapshots,
    )
