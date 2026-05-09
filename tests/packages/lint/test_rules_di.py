"""Branch-coverage tests for `a2kit.packages.lint.rules.di`.

Complements ``test_di_rules.py`` — covers AST-shape edge cases (attribute-form
``Depends``, nested ``Annotated`` tuples, ``noqa`` suppression, fixture-path
short-circuit, kw-only depends with defaults, posonly tool params, etc.) that
the original tests don't exercise.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import (
    A2K_DI_ANNOTATED,
    A2K_DI_IMPORT_LEGACY,
    A2K_DI_IMPORT_SLOW,
    A2K_DI_KWONLY,
    A2K_DI_PYDANTIC_VALIDATE,
    run_static_rules,
)


def _write(tmp_path: Path, name: str, body: str, *, subdir: str = "src") -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- A2K-DI-ANNOTATED edges --------------------------- #


def test_di_annotated_via_attribute_form(tmp_path: Path) -> None:
    """`Annotated[T, fastmcp.Depends(fn)]` — attribute-form Depends still flags."""
    body = (
        "import a2kit\n"
        "from typing import Annotated\n"
        "import some_mod\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db: Annotated[int, some_mod.Depends(get_db)]) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED in _codes(findings)


def test_di_annotated_attribute_subscript_base(tmp_path: Path) -> None:
    """`typing.Annotated[...]` (attribute base) still flags."""
    body = (
        "import a2kit\n"
        "import typing\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db: typing.Annotated[int, Depends(get_db)]) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED in _codes(findings)


def test_di_annotated_no_depends_marker(tmp_path: Path) -> None:
    """`Annotated[T, Field(...)]` without Depends should NOT flag."""
    body = (
        "import a2kit\n"
        "from typing import Annotated\n"
        "from pydantic import Field\n"
        "@a2kit.tool()\n"
        "def t(*, x: Annotated[int, Field(gt=0)]) -> int:\n"
        "    return x\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED not in _codes(findings)


def test_di_annotated_non_subscript_annotation(tmp_path: Path) -> None:
    """Plain annotation (no subscript) — short-circuits early, no findings."""
    body = "import a2kit\n@a2kit.tool()\ndef t(*, x: int) -> int:\n    return x\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED not in _codes(findings)


def test_di_annotated_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from typing import Annotated\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db: Annotated[int, Depends(get_db)]) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED not in _codes(findings)


def test_di_annotated_noqa_suppresses(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from typing import Annotated\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(\n"
        "    *,\n"
        "    db: Annotated[int, Depends(get_db)],  # noqa: A2K-DI-ANNOTATED\n"
        ") -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED not in _codes(findings)


# --------------------------- A2K-DI-IMPORT-* edges --------------------------- #


def test_di_import_legacy_other_import_silent(tmp_path: Path) -> None:
    """`from a2kit.di import Foo` (no Depends) — no finding."""
    body = "from a2kit.di import Foo\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_LEGACY not in _codes(findings)


def test_di_import_legacy_noqa(tmp_path: Path) -> None:
    body = "from a2kit.di import Depends  # noqa: A2K-DI-IMPORT-LEGACY\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_LEGACY not in _codes(findings)


def test_di_import_slow_other_import_silent(tmp_path: Path) -> None:
    body = "from fastmcp.dependencies import Other\n"
    p = _write(tmp_path, "m.py", body, subdir="src/a2kit/packages/mcp")
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_SLOW not in _codes(findings)


def test_di_import_slow_noqa(tmp_path: Path) -> None:
    body = "from fastmcp.dependencies import Depends  # noqa: A2K-DI-IMPORT-SLOW\n"
    p = _write(tmp_path, "m.py", body, subdir="src/a2kit/packages/mcp")
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_SLOW not in _codes(findings)


# --------------------------- A2K-DI-KWONLY edges --------------------------- #


def test_di_kwonly_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(db = Depends(get_db)) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY not in _codes(findings)


def test_di_kwonly_no_defaults_silent(tmp_path: Path) -> None:
    """Tool with no defaults at all — short-circuit branch."""
    body = "import a2kit\n@a2kit.tool()\ndef t(x: int) -> int:\n    return x\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY not in _codes(findings)


def test_di_kwonly_non_depends_default_silent(tmp_path: Path) -> None:
    """Positional default that is NOT Depends(...) — silent."""
    body = "import a2kit\n@a2kit.tool()\ndef t(x: int = 1) -> int:\n    return x\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY not in _codes(findings)


def test_di_kwonly_noqa_suppresses(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(db = Depends(get_db)) -> int:  # noqa: A2K-DI-KWONLY\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY not in _codes(findings)


def test_di_kwonly_attr_form_depends(tmp_path: Path) -> None:
    """`x = pkg.Depends(fn)` positional default — attribute form path."""
    body = "import a2kit\nimport pkg\ndef get_db(): ...\n@a2kit.tool()\ndef t(db = pkg.Depends(get_db)) -> int:\n    return 1\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY in _codes(findings)


# --------------------------- A2K-DI-PYDANTIC-VALIDATE edges --------------------------- #


def test_di_pydantic_validate_no_args_silent(tmp_path: Path) -> None:
    """`pydantic.validate_call()` with no positional arg — silent."""
    body = "import pydantic\npydantic.validate_call()\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_unknown_target_silent(tmp_path: Path) -> None:
    """validate_call(some_call()) where target isn't a Name — silent."""
    body = "import pydantic\ndef factory(): ...\npydantic.validate_call(factory())\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_target_fn_missing_silent(tmp_path: Path) -> None:
    """validate_call(undefined_fn) — `_function_def_at` returns None branch."""
    body = "import pydantic\npydantic.validate_call(unknown_fn)\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_bare_validate_call_no_pydantic_import_silent(tmp_path: Path) -> None:
    """Bare `validate_call(fn)` without pydantic-sourced import — silent (Name path skipped)."""
    body = (
        "from somewhere_else import validate_call\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_kw_default_depends(tmp_path: Path) -> None:
    """kw_defaults branch: kw-only param with Depends default — `_function_has_depends_default` over kw_defaults."""
    body = (
        "import pydantic\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = pydantic.validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE in _codes(findings)


def test_di_pydantic_validate_async_target(tmp_path: Path) -> None:
    """Async def target with Depends default — AsyncFunctionDef branch."""
    body = (
        "import pydantic\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "async def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = pydantic.validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE in _codes(findings)


def test_di_pydantic_validate_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = (
        "import pydantic\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = pydantic.validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body, subdir="tests/fixtures")
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_noqa(tmp_path: Path) -> None:
    body = (
        "import pydantic\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = pydantic.validate_call(fn)  # noqa: A2K-DI-PYDANTIC-VALIDATE\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_non_call_node_skipped(tmp_path: Path) -> None:
    """Non-Call AST nodes are skipped — covered by exhaustive ast.walk on a clean file."""
    body = "x = 1\ny = 2\nz = x + y\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)
