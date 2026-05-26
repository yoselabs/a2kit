"""Capability: surfaces are PASSIVE — surface module front doors execute
only imports + lazy `__getattr__` + `__all__`. No top-level registry
mutation. Per `bootstrap-surfaces-explicit` (2026-05-26).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PACKAGES_DIR = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages"


def _surface_package_inits() -> list[Path]:
    """Discover package `__init__.py` files for surface packages (mcp, http).

    Other packages may legitimately have non-import top-level statements;
    surface packages specifically are constrained by this requirement.
    """
    return [
        _PACKAGES_DIR / "mcp" / "__init__.py",
        _PACKAGES_DIR / "http" / "__init__.py",
    ]


@pytest.mark.parametrize("init_path", _surface_package_inits(), ids=lambda p: p.parent.name)
def test_surface_package_init_has_no_call_expressions(init_path: Path) -> None:
    """Top-level statements MUST be imports, `__getattr__`/`__dir__` defs,
    `__all__` assignments, or constant assignments — NO function/method calls.
    A call expression at module top-level is exactly the smell this
    requirement forbids (e.g., the old `SURFACE_REGISTRY.register_surface(...)`).
    """
    tree = ast.parse(init_path.read_text())
    call_sites: list[str] = []
    for node in tree.body:
        # Imports OK.
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        # __getattr__ / __dir__ / future facade defs OK.
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        # ClassDef would be A2K-PKG-INIT-IMPL violation, not ours; skip.
        if isinstance(node, ast.ClassDef):
            continue
        # If-blocks at top-level: walk inside for any Call expr.
        if isinstance(node, ast.If):
            call_sites.extend(f"line {sub.lineno}: call in top-level `if` block" for sub in ast.walk(node) if isinstance(sub, ast.Call))
        # Plain Expr nodes wrapping a Call are explicit side effects.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call_sites.append(f"line {node.lineno}: top-level call expression")
        # Assignments that call a function on the RHS (e.g. `X = foo()`)
        # are subtler; allow constant-only RHS but flag Call RHS.
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            # Allow `__all__ = [...]` and similar literal-list/tuple assigns;
            # disallow function-call RHS at top level.
            call_sites.append(f"line {node.lineno}: top-level assignment with call on RHS")
    assert not call_sites, (
        f"{init_path.relative_to(_PACKAGES_DIR.parent.parent.parent)}: surface package has top-level side effects: {call_sites}"
    )
