"""BDD: DI package is standalone-shippable — no a2kit imports inside.

Covers spec ``di-container-package``: the package at ``src/a2kit/packages/di/``
SHALL contain zero ``from a2kit`` / ``import a2kit`` references (excluding
self-references inside the package). This enables future extraction to a
standalone PyPI library.
"""

from __future__ import annotations

import re
from pathlib import Path


DI_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages" / "di"


def test_no_a2kit_imports_inside_di_package() -> None:
    """Grep ``src/a2kit/packages/di/`` for non-self-referential a2kit imports.

    Self-references inside the ``a2kit.packages.di.*`` namespace are allowed
    (the package's own internal modules import from each other). Any other
    ``from a2kit`` / ``import a2kit`` is forbidden.
    """
    assert DI_PACKAGE_ROOT.exists(), f"DI package not found at {DI_PACKAGE_ROOT}"

    pattern = re.compile(r"^\s*(from a2kit|import a2kit)\b", re.MULTILINE)
    self_ref_pattern = re.compile(r"a2kit\.packages\.di\b")

    offenders: list[tuple[Path, int, str]] = []
    for py_file in DI_PACKAGE_ROOT.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start : line_end if line_end != -1 else None]
            if self_ref_pattern.search(line):
                continue
            line_no = text[: match.start()].count("\n") + 1
            offenders.append((py_file, line_no, line.strip()))

    assert not offenders, "DI package must be self-contained for standalone shipping. Found:\n" + "\n".join(
        f"  {p}:{ln}: {src}" for p, ln, src in offenders
    )
