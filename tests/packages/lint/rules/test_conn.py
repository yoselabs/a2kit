"""Tests for `a2kit.packages.lint.rules.conn`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import (
    A2K014,
    A2K_CONN_LIST_PLACEHOLDER,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: test helper accepts findings as `object` to match the broad return contract of upstream lint runners


# --------------------------- conn.py: tuple/dict shapes --------------------------- #


def test_conn_list_placeholder_in_tuple(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: tuple = ('${MY_TAG}', 'plain')\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_in_set(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: set = {'${MY_TAG}', 'plain'}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_nested_dict_value(tmp_path: Path) -> None:
    """Recursion into nested list inside dict value."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    headers: dict = {'auth': ['${TOKEN}']}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_dict_key_with_placeholder(tmp_path: Path) -> None:
    """Dict KEY containing ${VAR} also flags (covers the keys-walk branch)."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    map: dict = {'${TOKEN}': 'v'}\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list = ['${MY_TAG}']\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_no_value_silent(tmp_path: Path) -> None:
    """Type-only `AnnAssign` with no value (e.g. abstract field) — silent."""
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_non_collection_value_silent(tmp_path: Path) -> None:
    """`AnnAssign` value is a function call — not list/tuple/set/dict, silent."""
    body = (
        "from a2kit.connections import ConnectionConfig\ndef factory(): return []\nclass C(ConnectionConfig):\n    tags: list = factory()\n"
    )
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_noqa(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list = ['${MY_TAG}']  # noqa: AK206\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


# --------------------------- budget.py edges --------------------------- #


def test_a2k014_just_under_threshold_silent(tmp_path: Path) -> None:
    body = "x = 1\n" * 100
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K014 not in _codes(findings)


# --------------------------- A2K006 cross is wired through `run_static_rules` --------------------------- #
