"""Snapshot comparison helpers for public-API tier tests.

A "snapshot" is a sorted, newline-delimited list of public names stored
in a checked-in expectation file. The helpers here compare an observed
iterable of names against an expectation file, render a structured
failure message on drift, and support a regeneration mode that
overwrites the expectation file in place. See
``docs/adr/0004-package-layout-tiered-by-audience.md``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable


_REGEN_NOTE = "Regenerate with: pytest tests/surface --regen-snapshots"
_ADR_NOTE = (
    "If this change is intentional, update the expectation file AND "
    "file or amend ADR 0004 (docs/adr/0004-package-layout-tiered-by-audience.md) "
    "to justify the promotion."
)


def _render_lines(names: Iterable[str]) -> str:
    return "\n".join(sorted(set(names))) + "\n"


def _write_expectation(path: Path, names: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_lines(names), encoding="utf-8")


def _read_expectation(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {line for line in (raw.strip() for raw in text.splitlines()) if line}


def _format_failure(label: str, path: Path, added: set[str], removed: set[str]) -> str:
    parts = [f"Public surface of `{label}` drifted."]
    if added:
        parts.append(f"  ADDED:    {sorted(added)}")
    if removed:
        parts.append(f"  REMOVED:  {sorted(removed)}")
    parts.append(f"Expectation file: {path}")
    parts.append(_ADR_NOTE)
    parts.append(_REGEN_NOTE)
    return "\n".join(parts)


def assert_snapshot(
    label: str,
    observed: Iterable[str],
    expected_path: Path,
    *,
    regen: bool,
) -> None:
    """Assert observed names match the expectation, or regenerate.

    The expectation file is one public name per line, sorted. Names with
    a leading underscore are not filtered here — the caller decides what
    "public" means for the surface under test.

    When ``regen`` is true, the file is (re)written to match observation
    and no assertion is raised. The caller's pytest report will show the
    test as passing; the meaningful signal is the file diff under git.
    """

    if regen:
        _write_expectation(expected_path, observed)
        return

    if not expected_path.exists():
        raise AssertionError(f"Expectation file missing for `{label}`: {expected_path}\nCreate it by running: {_REGEN_NOTE}")

    observed_set = set(observed)
    expected_set = _read_expectation(expected_path)
    added = observed_set - expected_set
    removed = expected_set - observed_set
    if added or removed:
        raise AssertionError(_format_failure(label, expected_path, added, removed))
