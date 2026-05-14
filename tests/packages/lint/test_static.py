"""Smoke tests for ported static rules — they still fire on legacy patterns."""

from __future__ import annotations

from pathlib import Path

import pytest

from a2kit.packages.lint.static import (
    A2K002,
    A2K003,
    A2K011,
    A2K013,
    A2K014,
    run_static_rules,
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    """Write a Python file outside any tests/ or examples/ token."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    p = src_dir / name
    p.write_text(body, encoding="utf-8")
    return p


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: test helper accepts findings as `object` to match the broad return contract of upstream lint runners


def test_a2k002_str_return(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> str:\n    return 'x'\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 in _codes(findings)


def test_a2k003_local_pydantic_return(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from pydantic import BaseModel\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "@a2kit.write()\n"
        "def t() -> Out:\n"
        "    return Out(x=1)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 in _codes(findings)


def test_a2k011_dict_return(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> dict:\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 in _codes(findings)


def test_a2k013_manual_param_doc_in_docstring(tmp_path: Path) -> None:
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:\n    f"""Hello {a2kit.docs.param_doc(\'foo\')} bar."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 in _codes(findings)


def test_a2k014_too_long(tmp_path: Path) -> None:
    body = "x = 1\n" * 600
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K014 in _codes(findings)


def test_no_findings_on_clean_file(tmp_path: Path) -> None:
    body = "import a2kit\nfrom pydantic import BaseModel\n@a2kit.write()\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert findings == []


def test_noqa_suppresses_rule(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> str:  # noqa: A2K002\n    return 'x'\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 not in _codes(findings)


def test_disabled_rule_not_run(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> str:\n    return 'x'\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p], disabled=[A2K002])
    assert A2K002 not in _codes(findings)


@pytest.mark.parametrize("missing", ["nonexistent.py"])
def test_missing_files_skipped_gracefully(tmp_path: Path, missing: str) -> None:
    findings = run_static_rules([tmp_path / missing])
    assert findings == []
