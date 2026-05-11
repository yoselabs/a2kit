"""Tests for `a2kit.packages.lint.rules.caps`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.rules.caps import _reset_reexport_cache
from a2kit.packages.lint.static import (
    A2K009,
    A2K012,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- caps.py: re-export resolution --------------------------- #


def test_a2k012_silent_for_local_final_str_constant(tmp_path: Path) -> None:
    """Custom capability passed as `Final[str]` Name → silent."""
    _write(tmp_path / "src" / "pyproject.toml", "")
    body = (
        "from typing import Final\n"
        "import a2kit\n"
        "MY_CAP: Final[str] = 'my-cap'\n"
        "@a2kit.tool(capabilities={MY_CAP})\n"
        "def t() -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_silent_for_imported_final_str(tmp_path: Path) -> None:
    """Constant imported from a sibling module that declares it as Final[str]."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    _write(
        tmp_path / "src" / "caps_lib.py",
        "from typing import Final\nMY_CAP: Final[str] = 'my-cap'\n",
    )
    body = "import a2kit\nfrom caps_lib import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_resolves_through_reexport_chain(tmp_path: Path) -> None:
    """A → B re-export → C declares Final[str]. Cache also gets exercised on second call."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    # Package layout:
    #   src/pkg/__init__.py re-exports MY_CAP from pkg.middle
    #   src/pkg/middle.py re-exports MY_CAP from pkg.leaf
    #   src/pkg/leaf.py declares Final[str]
    _write(tmp_path / "src" / "pkg" / "__init__.py", "from pkg.middle import MY_CAP\n")
    _write(tmp_path / "src" / "pkg" / "middle.py", "from pkg.leaf import MY_CAP\n")
    _write(
        tmp_path / "src" / "pkg" / "leaf.py",
        "from typing import Final\nMY_CAP: Final[str] = 'deep'\n",
    )
    body = "import a2kit\nfrom pkg import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings1 = run_static_rules([p])
    findings2 = run_static_rules([p])  # second hit uses cache
    assert A2K012 not in _codes(findings1)
    assert A2K012 not in _codes(findings2)


def test_a2k012_unresolved_reexport_falls_back_to_constant_str(tmp_path: Path) -> None:
    """Cap is given as a raw string literal (not a Name) and there's no constant — A2K012 fires."""
    _reset_reexport_cache()
    _write(tmp_path / "src" / "pyproject.toml", "")
    body = "import a2kit\n@a2kit.tool(capabilities={'unknown-cap'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 in _codes(findings)


def test_a2k009_in_list_and_tuple_containers(tmp_path: Path) -> None:
    """`capabilities=['read']` and `capabilities=('read',)` both flag."""
    _write(tmp_path / "src" / "pyproject.toml", "")
    body_list = "import a2kit\n@a2kit.tool(capabilities=['read'])\ndef t() -> int:\n    return 1\n"
    body_tuple = "import a2kit\n@a2kit.tool(capabilities=('read',))\ndef u() -> int:\n    return 1\n"
    p1 = _write(tmp_path / "src" / "m1.py", body_list)
    p2 = _write(tmp_path / "src" / "m2.py", body_tuple)
    findings1 = run_static_rules([p1])
    findings2 = run_static_rules([p2])
    assert A2K009 in _codes(findings1)
    assert A2K009 in _codes(findings2)


def test_a2k009_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K009 not in _codes(findings)


def test_a2k009_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})  # noqa: A2K009\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K009 not in _codes(findings)


def test_a2k012_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={'unknown'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_a2k012_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool(capabilities={\n    'unknown',  # noqa: A2K012\n})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K012 not in _codes(findings)


def test_collect_local_final_str_names_handles_pathological_shapes() -> None:
    """Direct test of `_collect_local_final_str_names` over weird AST shapes."""
    import ast

    from a2kit.packages.lint.rules.caps import _collect_local_final_str_names

    # Non-module input (line 144) → empty set.
    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _collect_local_final_str_names(expr_tree) == set()

    # AnnAssign without Subscript annotation (line 150).
    src = "from typing import Final\nMY: Final = 'x'\n"
    assert _collect_local_final_str_names(ast.parse(src)) == set()

    # Subscript base != Final (line 154).
    src2 = "from typing import List\nMY: List[str] = ['x']\n"
    assert _collect_local_final_str_names(ast.parse(src2)) == set()

    # slice is not a Name (e.g. Subscript) (line 156).
    src3 = "from typing import Final\nMY: Final[list[str]] = ['x']\n"
    assert _collect_local_final_str_names(ast.parse(src3)) == set()

    # Plain assignments (not AnnAssign) — also skipped.
    src4 = "MY = 'x'\n"
    assert _collect_local_final_str_names(ast.parse(src4)) == set()

    # AnnAssign target not a Name (e.g. Tuple/Subscript) — skipped.
    src5 = "from typing import Final\nx: Final[str]\n"  # no value, but still caught
    assert _collect_local_final_str_names(ast.parse(src5)) == {"x"}


def test_module_to_path_returns_none_for_unknown_module(tmp_path: Path) -> None:
    """Direct test of `_module_to_path` with a non-existent module."""
    from a2kit.packages.lint.rules.caps import _module_to_path

    assert _module_to_path("not_a_real_module", tmp_path) is None


def test_has_final_str_assign_handles_non_module() -> None:
    import ast

    from a2kit.packages.lint.rules.caps import _has_final_str_assign

    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _has_final_str_assign(expr_tree, "X") is False


def test_find_reexport_handles_non_module() -> None:
    import ast

    from a2kit.packages.lint.rules.caps import _find_reexport

    expr_tree = ast.parse("1 + 1", mode="eval")
    assert _find_reexport(expr_tree, "X") is None


def test_a2k012_silent_for_builtin_string_in_set(tmp_path: Path) -> None:
    """Built-in caps in `capabilities` set raise A2K009 not A2K012 — A2K012 short-circuits."""
    body = "import a2kit\n@a2kit.tool(capabilities={'read'})\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path / "src" / "m.py", body)
    findings = run_static_rules([p])
    # A2K009 fires; A2K012 does NOT fire on built-ins.
    assert A2K009 in _codes(findings)
    assert A2K012 not in _codes(findings)
