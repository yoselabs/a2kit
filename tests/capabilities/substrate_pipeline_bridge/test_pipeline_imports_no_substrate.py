"""Capability: `packages/dispatch/` imports no substrate-specific library.

The dispatch pipeline is transport-neutral. It MUST NOT import fastapi,
starlette, or fastmcp — substrates are observed only through the two named
ContextVars (`request_scope`, `_render_state`).
"""

from __future__ import annotations

import ast
from pathlib import Path

_DISPATCH_DIR = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages" / "dispatch"

_FORBIDDEN_TOP_LEVELS = {"fastapi", "starlette", "fastmcp"}


def _iter_module_imports(path: Path) -> list[tuple[int, str]]:
    """Yield (lineno, top-level module name) for every import in the file."""
    tree = ast.parse(path.read_text())
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend((node.lineno, alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.lineno, node.module.split(".")[0]))
    return out


def test_dispatch_modules_never_import_substrate_libraries() -> None:
    """Walk every .py under `packages/dispatch/` and assert no forbidden top-level import."""
    violations: list[str] = [
        f"{path.relative_to(_DISPATCH_DIR.parents[3])}:{lineno} imports {top!r}"
        for path in _DISPATCH_DIR.rglob("*.py")
        for lineno, top in _iter_module_imports(path)
        if top in _FORBIDDEN_TOP_LEVELS
    ]
    assert not violations, "dispatch/ leaks substrate imports:\n" + "\n".join(violations)
