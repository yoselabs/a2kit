"""A2K-CORE-PURITY — core ``src/a2kit/`` MUST NOT import from ``a2kit.packages.*``.

The inverse of ``A2K-IMPORT-DISCIPLINE`` (which forbids fastmcp imports
outside ``packages/mcp``). Together they enforce the layering: core knows
no packages; packages know each other and core.

Files in ``src/a2kit/packages/**`` are NOT subject to this rule (they ARE
the packages). The rule walks runtime ``import`` / ``from ... import``
nodes — ``if TYPE_CHECKING:`` blocks are safe (those don't hit at runtime,
and removing the type imports would force redundant string annotations).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage


def _is_core_path(filename: str) -> bool:
    return ("/src/a2kit/" in filename or filename.startswith("src/a2kit/")) and (
        "/src/a2kit/packages/" not in filename and not filename.startswith("src/a2kit/packages/")
    )


def _module_targets_package(module: str | None) -> bool:
    return module is not None and (module == "a2kit.packages" or module.startswith("a2kit.packages."))


def _under_type_checking(stack: list[ast.AST]) -> bool:
    for node in stack:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            return True
    return False


def _under_function_body(stack: list[ast.AST]) -> bool:
    """Function-body imports are lazy (don't fire at module load).

    They preserve the cold-start invariant — ``import a2kit`` doesn't pull
    package code unless a runtime entry point is actually invoked. The rule
    treats function-body imports as exempt; module-level imports remain a
    violation.
    """
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in stack)


def rule_a2k_core_purity(tree: ast.AST, filename: str, _source: str) -> Iterable[LintMessage]:
    from a2kit.packages.lint.static import A2K_CORE_PURITY, LintMessage

    if not _is_core_path(filename):
        return

    # Walk with parent stack to detect TYPE_CHECKING-guarded imports.
    stack: list[ast.AST] = []

    def visit(node: ast.AST) -> Iterable[LintMessage]:
        stack.append(node)
        try:
            if isinstance(node, ast.ImportFrom):
                if _module_targets_package(node.module) and not (_under_type_checking(stack) or _under_function_body(stack)):
                    yield LintMessage(
                        rule=A2K_CORE_PURITY,
                        filename=filename,
                        line=node.lineno,
                        col=node.col_offset,
                        message=(
                            f"core file imports from {node.module!r}; core must not depend on packages. "
                            "Move the dependency into a plugin or invert the import direction."
                        ),
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_targets_package(alias.name) and not (_under_type_checking(stack) or _under_function_body(stack)):
                        yield LintMessage(
                            rule=A2K_CORE_PURITY,
                            filename=filename,
                            line=node.lineno,
                            col=node.col_offset,
                            message=(f"core file imports {alias.name!r}; core must not depend on packages."),
                        )
            for child in ast.iter_child_nodes(node):
                yield from visit(child)
        finally:
            stack.pop()

    yield from visit(tree)


__all__ = ["rule_a2k_core_purity"]
