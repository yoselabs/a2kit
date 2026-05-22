"""Tests for `a2kit.packages.lint.rules.importing`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import (
    A2K_IMPORT_DISCIPLINE,
    A2K_PKG_INIT_IMPORT,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: test helper accepts findings as `object` to match the broad return contract of upstream lint runners


# --------------------------- importing.py: allowlist edges --------------------------- #


def test_import_discipline_plain_import_form_fires(tmp_path: Path) -> None:
    """`import fastmcp` (Import, not ImportFrom) outside allowlist."""
    body = "import fastmcp\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_dotted_module_fires(tmp_path: Path) -> None:
    """`import fastmcp.server` is also covered."""
    body = "import fastmcp.server\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_other_imports_silent(tmp_path: Path) -> None:
    body = "import os\nfrom typing import Any\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_otel_dir(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "otel" / "middleware.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_cli_context(tmp_path: Path) -> None:
    """``packages/cli/context.py`` is allowlisted for the lazy elicit() import."""
    body = "from fastmcp.server.elicitation import AcceptedElicitation\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "cli" / "context.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_user_tool_with_fastmcp_context_annotation_is_silent(tmp_path: Path) -> None:
    """Tool annotations ``ctx: fastmcp.Context`` import fastmcp at module top.

    User code under their own package isn't subject to A2K-IMPORT-DISCIPLINE
    (the rule only fires inside ``a2kit/``). This regression locks that in
    so portable tool authors aren't penalized for using the real type.
    """
    body = "from fastmcp import Context\nasync def my_tool(*, ctx: Context) -> dict:\n    return {}\n"
    p = _write(tmp_path / "user_app" / "tools.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_noqa(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP  # noqa: A2K-IMPORT-DISCIPLINE\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


# ----------------------- importing.py: A2K-PKG-INIT-IMPORT ----------------------- #


def test_pkg_init_absolute_self_import_fires(tmp_path: Path) -> None:
    """A submodule doing `from a2kit.<...>.<pkg> import X` is flagged."""
    body = "from a2kit.packages.formatter import render\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT in _codes(findings)


def test_pkg_init_relative_self_import_fires(tmp_path: Path) -> None:
    """`from . import X` pulls the package `__init__` — flagged."""
    body = "from . import render\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT in _codes(findings)


def test_pkg_init_sibling_import_is_silent(tmp_path: Path) -> None:
    """Importing a sibling submodule (`from .formats import X`) is allowed."""
    body = "from .formats import FormatName\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_cross_package_import_is_silent(tmp_path: Path) -> None:
    """Importing from another package is allowed."""
    body = "from a2kit.packages.di import container\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_self_import_in_init_is_silent(tmp_path: Path) -> None:
    """A package `__init__.py` re-exporting its own submodules is allowed."""
    body = "from .render import render\nfrom a2kit.packages.formatter import render as r2\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_import_noqa(tmp_path: Path) -> None:
    body = "from . import render  # noqa: A2K-PKG-INIT-IMPORT\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)
