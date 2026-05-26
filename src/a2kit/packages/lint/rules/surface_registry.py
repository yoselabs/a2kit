"""A2K-SURFACE-REGISTRY — every ``Surface``-shaped class ships a MANIFEST.

Fires when a class subclassing ``DecoratorSurface`` lands in a package
that does not also export a module-level ``MANIFEST = PluginManifest(...)``
constant for it. The MANIFEST shape (per ``adopt-plugin-manifests``) is
how new surface plugins are discoverable; classes without a MANIFEST
are invisible to `load_surface(...)`.

Rule code: ``A2K-SURFACE-REGISTRY``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage


_SURFACE_BASE_NAMES = frozenset({"DecoratorSurface"})


def _is_surface_base(base: ast.expr) -> bool:
    """``DecoratorSurface[X]`` or ``DecoratorSurface`` in any import form."""
    target = base
    if isinstance(base, ast.Subscript):
        target = base.value
    if isinstance(target, ast.Name):
        return target.id in _SURFACE_BASE_NAMES
    if isinstance(target, ast.Attribute):
        return target.attr in _SURFACE_BASE_NAMES
    return False


def _module_declares_manifest(tree: ast.AST) -> bool:
    """True iff the module body assigns a top-level name ``MANIFEST``."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MANIFEST":
                    return True
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "MANIFEST":
            return True
    return False


def rule_surface_registry(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """Yield A2K-SURFACE-REGISTRY findings for the given module AST."""
    del source  # unused; required by signature
    from a2kit.packages.lint.static import A2K_SURFACE_REGISTRY, LintMessage

    body = tree.body if isinstance(tree, ast.Module) else []
    surface_classes = [node for node in body if isinstance(node, ast.ClassDef) and any(_is_surface_base(b) for b in node.bases)]
    if not surface_classes:
        return
    if _module_declares_manifest(tree):
        return
    for cls in surface_classes:
        yield LintMessage(
            rule=A2K_SURFACE_REGISTRY,
            filename=filename,
            line=cls.lineno,
            col=cls.col_offset,
            message=(
                f"class {cls.name!r} subclasses DecoratorSurface but the module "
                "does not export a `MANIFEST = PluginManifest(...)` constant. "
                "Surfaces without a MANIFEST are invisible to load_surface(); "
                "add one alongside the class."
            ),
        )


__all__ = ["rule_surface_registry"]
