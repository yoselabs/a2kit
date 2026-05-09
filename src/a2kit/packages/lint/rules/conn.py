"""Connection-shape rules.

- A2K-CONN-LIST-PLACEHOLDER — ``${VAR}`` inside list/dict on ``ConnectionConfig``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K_CONN_LIST_PLACEHOLDER,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def _connection_config_classes(tree: ast.AST) -> list[ast.ClassDef]:
    out: list[ast.ClassDef] = []
    if not isinstance(tree, ast.Module):
        return out
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            name = base.attr if isinstance(base, ast.Attribute) else (base.id if isinstance(base, ast.Name) else None)
            if name == "ConnectionConfig":
                out.append(node)
                break
    return out


def _walk_for_var_placeholders(node: ast.expr) -> Iterable[ast.Constant]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and "${" in node.value:
        yield node
        return
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            yield from _walk_for_var_placeholders(elt)
        return
    if isinstance(node, ast.Dict):
        for k in node.keys:
            if k is not None:
                yield from _walk_for_var_placeholders(k)
        for v in node.values:
            yield from _walk_for_var_placeholders(v)


def rule_conn_list_placeholder(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for cls in _connection_config_classes(tree):
        for stmt in cls.body:
            if not isinstance(stmt, ast.AnnAssign):
                continue
            value = stmt.value
            if not isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
                continue
            for hit in _walk_for_var_placeholders(value):
                if suppressed(noqa, A2K_CONN_LIST_PLACEHOLDER, hit.lineno):
                    continue
                yield _msg(
                    A2K_CONN_LIST_PLACEHOLDER,
                    filename,
                    hit,
                    (
                        "${VAR} substitution does not recurse into list/dict fields on ConnectionConfig. "
                        "Declare individual scalar fields, or post-process at the field validator level."
                    ),
                )


__all__ = ["rule_conn_list_placeholder"]
