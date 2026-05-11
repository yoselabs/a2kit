"""Tests for `a2kit.packages.lint.rules.budget`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import A2K014, run_static_rules


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


def test_a2k014_just_under_threshold_silent(tmp_path: Path) -> None:
    body = "x = 1\n" * 100
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K014 not in _codes(findings)
