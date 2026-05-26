"""Capability: every manifest module under `packages/auth/_providers/`
declares only the MANIFEST constant + protocol implementation; no
top-level side effects.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PROVIDERS_DIR = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages" / "auth" / "_providers"


def _provider_modules() -> list[Path]:
    return sorted(p for p in _PROVIDERS_DIR.glob("*.py") if p.name != "__init__.py")


def _classify_top_level(node: ast.stmt) -> str | None:  # noqa: PLR0911 -- one return per AST shape is the clearest form here
    """Return a violation message for ``node`` or None if the node is allowed.

    Allowed at a manifest module's top level:
      - imports (Import / ImportFrom)
      - class / function / async-function definitions
      - assignments (MANIFEST, type aliases) — except ones whose RHS is
        a non-``PluginManifest`` call (which would invoke a factory at
        import time)
      - the module docstring (an Expr whose value is a string constant)
      - ``if TYPE_CHECKING:`` guards (body never runs at runtime)
    """
    if isinstance(node, ast.Import | ast.ImportFrom | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return None
    if isinstance(node, ast.Assign | ast.AnnAssign):
        value = node.value
        if not isinstance(value, ast.Call):
            return None
        func = value.func
        func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else "<call>"
        if func_name != "PluginManifest":
            return f"line {node.lineno}: top-level call `{func_name}(...)`"
        return None
    if isinstance(node, ast.If):
        test = node.test
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return None
        return f"line {node.lineno}: top-level `if` (only `if TYPE_CHECKING:` is allowed)"
    if isinstance(node, ast.Expr):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return f"line {node.lineno}: top-level expression"
    return f"line {node.lineno}: unexpected top-level statement {type(node).__name__}"


@pytest.mark.parametrize("module_path", _provider_modules(), ids=lambda p: p.stem)
def test_manifest_module_top_level_is_pure(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text())
    offenders = [msg for node in tree.body if (msg := _classify_top_level(node)) is not None]
    assert not offenders, f"{module_path.name}: manifest module must be side-effect-free at import time: {offenders}"
