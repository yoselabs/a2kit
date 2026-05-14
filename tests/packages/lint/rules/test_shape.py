"""Branch-coverage tests for `a2kit.packages.lint.rules.shape`.

Covers AST-shape edge cases for A2K002/A2K003/A2K011/A2K013 not exercised
by ``test_static.py``: noqa suppression, fixture-path short-circuits,
string-form annotations, ``ConnectionConfig``-based pydantic detection,
``dict[..]`` subscripts, and f-string vs plain-string docstrings.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import A2K002, A2K003, A2K011, A2K013, run_static_rules


def _write(tmp_path: Path, name: str, body: str, *, subdir: str = "src") -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: test helper accepts findings as `object` to match the broad return contract of upstream lint runners


# --------------------------- A2K002 (-> str) edges --------------------------- #


def test_a2k002_string_form_annotation(tmp_path: Path) -> None:
    """`-> "str"` (string-quoted annotation) still flags."""
    body = 'import a2kit\n@a2kit.write()\ndef t() -> "str":\n    return "x"\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 in _codes(findings)


def test_a2k002_no_returns_silent(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t():\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 not in _codes(findings)


def test_a2k002_non_str_return_silent(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 not in _codes(findings)


def test_a2k002_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> str:  # noqa: A2K002\n    return 'x'\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K002 not in _codes(findings)


# --------------------------- A2K003 edges --------------------------- #


def test_a2k003_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from pydantic import BaseModel\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "@a2kit.write()\n"
        "def t() -> Out:\n"
        "    return Out(x=1)\n"
    )
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K003 not in _codes(findings)


def test_a2k003_no_local_pydantic_short_circuits(tmp_path: Path) -> None:
    """No pydantic-base classes in the file — early return branch."""
    body = "import a2kit\n@a2kit.write()\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 not in _codes(findings)


def test_a2k003_attribute_base_class_pydantic(tmp_path: Path) -> None:
    """Class with `pydantic.BaseModel` (attribute-form base) — also detected."""
    body = (
        "import a2kit\nimport pydantic\nclass Out(pydantic.BaseModel):\n    x: int\n@a2kit.write()\ndef t() -> Out:\n    return Out(x=1)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 in _codes(findings)


def test_a2k003_connection_config_base_class(tmp_path: Path) -> None:
    """ConnectionConfig-derived class is treated as 'local pydantic' for A2K003 too."""
    body = (
        "import a2kit\n"
        "from a2kit.connections import ConnectionConfig\n"
        "class Out(ConnectionConfig):\n"
        "    x: int = 1\n"
        "@a2kit.write()\n"
        "def t() -> Out:\n"
        "    return Out()\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 in _codes(findings)


def test_a2k003_returns_unrelated_class_silent(tmp_path: Path) -> None:
    """Class is local pydantic but tool returns a different type — silent."""
    body = (
        "import a2kit\nfrom pydantic import BaseModel\nclass Out(BaseModel):\n    x: int\n@a2kit.write()\ndef t() -> int:\n    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 not in _codes(findings)


def test_a2k003_noqa(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from pydantic import BaseModel\n"
        "class Out(BaseModel):\n"
        "    x: int\n"
        "@a2kit.write()\n"
        "def t() -> Out:  # noqa: A2K003\n"
        "    return Out(x=1)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K003 not in _codes(findings)


# --------------------------- A2K011 edges --------------------------- #


def test_a2k011_dict_subscript(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> dict[str, int]:\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 in _codes(findings)


def test_a2k011_mapping_return(tmp_path: Path) -> None:
    body = "import a2kit\nfrom typing import Mapping\n@a2kit.write()\ndef t() -> Mapping:\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 in _codes(findings)


def test_a2k011_capital_dict_alias(tmp_path: Path) -> None:
    body = "import a2kit\nfrom typing import Dict\n@a2kit.write()\ndef t() -> Dict[str, int]:\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 in _codes(findings)


def test_a2k011_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> dict:\n    return {}\n"
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K011 not in _codes(findings)


def test_a2k011_noqa(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> dict:  # noqa: A2K011\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 not in _codes(findings)


def test_a2k011_no_returns_silent(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t():\n    return {}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 not in _codes(findings)


def test_a2k011_unrelated_subscript_silent(tmp_path: Path) -> None:
    """`list[int]` return — A2K011 silent (not dict/Mapping)."""
    body = "import a2kit\n@a2kit.write()\ndef t() -> list[int]:\n    return [1]\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K011 not in _codes(findings)


# --------------------------- A2K013 edges --------------------------- #


def test_a2k013_plain_string_docstring(tmp_path: Path) -> None:
    """Plain string docstring (not f-string) containing the marker."""
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:\n    """Use a2kit.docs.param_doc(\'foo\') here."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 in _codes(findings)


def test_a2k013_connection_param_doc_marker(tmp_path: Path) -> None:
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:\n    """uses a2kit.docs.connection_param_doc(\'x\')."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 in _codes(findings)


def test_a2k013_no_docstring_silent(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.write()\ndef t() -> int:\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_non_string_first_stmt_silent(tmp_path: Path) -> None:
    """First body stmt is `pass`, not an Expr — `_first_doc_text` returns ""."""
    body = "import a2kit\n@a2kit.write()\ndef t() -> int:\n    pass\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_expr_non_string_constant_silent(tmp_path: Path) -> None:
    """First Expr is a numeric constant — `_first_doc_text` returns ""."""
    body = "import a2kit\n@a2kit.write()\ndef t() -> int:\n    42\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_docstring_without_marker_silent(tmp_path: Path) -> None:
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:\n    """ordinary docstring without markers."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:\n    """uses a2kit.docs.param_doc(\'x\')."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_noqa(tmp_path: Path) -> None:
    body = 'import a2kit\n@a2kit.write()\ndef t() -> int:  # noqa: A2K013\n    """uses a2kit.docs.param_doc(\'x\')."""\n    return 1\n'
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 not in _codes(findings)


def test_a2k013_fstring_with_formatted_value(tmp_path: Path) -> None:
    """f-string docstring with a FormattedValue piece (covers JoinedStr branch)."""
    body = (
        "import a2kit\n"
        "VAR = 'x'\n"
        "@a2kit.write()\n"
        "def t() -> int:\n"
        '    f"""prefix {VAR} a2kit.docs.param_doc(\'foo\') suffix"""\n'
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K013 in _codes(findings)
