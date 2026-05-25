"""_LAZY_ATTRS keys snapshot.

A separate snapshot of ``src/a2kit/__init__.py``'s ``_LAZY_ATTRS`` keys.
Catches additions to the lazy registry even before any consumer
resolves them. Required because Tier-1 surface drift typically starts
as a one-line edit to the ``_LAZY_ATTRS`` dict literal.
"""

from __future__ import annotations

from pathlib import Path

import a2kit

from tests.surface._snapshot import assert_snapshot

_EXPECTED_PATH = Path(__file__).parent / "expected_lazy_attrs.txt"


def test_lazy_attrs_keys_match_snapshot(regen_snapshots: bool) -> None:
    keys = list(a2kit._LAZY_ATTRS.keys())  # type: ignore[attr-defined]
    assert_snapshot(
        "a2kit._LAZY_ATTRS",
        keys,
        _EXPECTED_PATH,
        regen=regen_snapshots,
    )
