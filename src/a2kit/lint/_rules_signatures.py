"""Rules that inspect tool function signatures.

A2K001 — `connection_param='X'` requires param X on the function.
A2K004 — Tool with `connection` param should reference `connection_param_doc`.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import (
    decorator_kwargs,
    function_has_param,
    is_a2kit_tool_decorator,
    is_tool_function,
)
from a2kit.lint._common import (
    A2K001,
    A2K004,
    is_fixture_path,
    msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.lint._common import LintMessage


def rule_a2k001(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K001 — `@a2kit.tool(connection_param='X')` requires param X on the function."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not is_a2kit_tool_decorator(dec):
                continue
            cp = decorator_kwargs(dec).get("connection_param")
            if not isinstance(cp, ast.Constant) or not isinstance(cp.value, str):
                continue
            if not function_has_param(node, cp.value) and not suppressed(noqa, A2K001, node.lineno):
                yield msg(A2K001, filename, node, f"function {node.name!r} missing connection_param {cp.value!r}")


def rule_a2k004(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K004 — Tools with `connection` param should reference the canonical helper."""
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    if "connection_param_doc" in source:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or not function_has_param(node, "connection"):
            continue
        if suppressed(noqa, A2K004, node.lineno):
            continue
        yield msg(
            A2K004,
            filename,
            node,
            f"tool {node.name!r} has `connection` param but no a2kit.docs.connection_param_doc reference",
        )


__all__ = ["rule_a2k001", "rule_a2k004"]
