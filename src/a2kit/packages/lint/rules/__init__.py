"""Per-family lint rule modules + shared AST helpers.

Each rule module exposes one or more ``_rule_*`` generators with the signature
``(tree, filename, source) -> Iterable[LintMessage]``. Shared helpers below are
used across families (tool detection, import inspection).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable


def is_a2kit_tool_decorator(dec: ast.expr) -> bool:
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    if isinstance(target, ast.Attribute):
        return target.attr == "tool" and isinstance(target.value, ast.Name) and target.value.id in {"a2kit", "tools"}
    if isinstance(target, ast.Name):
        return target.id == "tool"
    return False


def is_server_tool_decorator(dec: ast.expr) -> bool:
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    return isinstance(target, ast.Attribute) and target.attr == "tool"


def is_tool_function(node: ast.AST) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(is_a2kit_tool_decorator(d) or is_server_tool_decorator(d) for d in node.decorator_list)


def collect_import_sources(tree: ast.AST) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local = alias.asname or alias.name
                out[local] = (node.module, alias.name)
    return out


def iter_string_literals(node: ast.expr) -> Iterable[ast.Constant]:
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                yield elt


__all__ = [
    "collect_import_sources",
    "is_a2kit_tool_decorator",
    "is_server_tool_decorator",
    "is_tool_function",
    "iter_string_literals",
]
