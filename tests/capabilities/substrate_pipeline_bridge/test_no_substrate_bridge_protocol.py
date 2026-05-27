"""Capability: the substrate<->pipeline contract lives as documentation + capability tests, NOT as a Protocol class.

Per `dispatch-pipeline-parity-on-http` design Decision 3: extracting a
`SubstrateBridge(Protocol)` is premature with one user (HTTP migrating). The
contract is enforced by these capability tests. Promotion to a Protocol
happens when a third substrate exercises it.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_SRC = Path(__file__).resolve().parents[3] / "src"


def test_no_substrate_bridge_protocol_class_exists() -> None:
    """No `class SubstrateBridge` anywhere under src/."""
    pattern = re.compile(r"class\s+SubstrateBridge\b")
    matches: list[str] = []
    for path in _REPO_SRC.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                matches.append(f"{path}:{lineno}: {line.strip()}")
    assert not matches, "unexpected SubstrateBridge class found:\n" + "\n".join(matches)


def test_no_protocol_lookalike_in_dispatch() -> None:
    """No 'Bridge' Protocol class under dispatch/ either — surfaces the wrong abstraction."""
    pattern = re.compile(r"class\s+\w*Bridge\s*\(\s*Protocol\b")
    dispatch = _REPO_SRC / "a2kit" / "packages" / "dispatch"
    matches: list[str] = [f"{p}: {line}" for p in dispatch.rglob("*.py") for line in p.read_text().splitlines() if pattern.search(line)]
    assert not matches, "unexpected *Bridge(Protocol) class in dispatch/:\n" + "\n".join(matches)
