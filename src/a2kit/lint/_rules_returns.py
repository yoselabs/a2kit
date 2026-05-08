"""Rules that inspect a tool function's return annotation.

A2K002 — `-> str` (FastMCP double-serialises).
A2K003 — local Pydantic model (schema snapshots can't introspect across files).
A2K011 — raw `dict`/`Mapping` (advisory: prefer a Pydantic model).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import is_tool_function, local_pydantic_classes
from a2kit.lint._common import (
    A2K002,
    A2K003,
    A2K011,
    is_fixture_path,
    msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.lint._common import LintMessage


def rule_a2k002(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K002 — Tools must not declare `-> str` return."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_str = (isinstance(ret, ast.Name) and ret.id == "str") or (isinstance(ret, ast.Constant) and ret.value == "str")
        if is_str and not suppressed(noqa, A2K002, node.lineno):
            yield msg(A2K002, filename, node, f"tool {node.name!r} declares `-> str`; FastMCP double-serialises")


def rule_a2k003(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K003 — Tools should not return locally-defined Pydantic models."""
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    locals_ = local_pydantic_classes(tree)
    if not locals_:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret_name = node.returns.id if isinstance(node.returns, ast.Name) else None
        if ret_name in locals_ and not suppressed(noqa, A2K003, node.lineno):
            yield msg(A2K003, filename, node, f"tool {node.name!r} returns module-local Pydantic model {ret_name!r}")


def rule_a2k011(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K011 — advisory: tool returns raw `dict`/`Mapping` instead of a Pydantic model.

    Skipped under tests/ and examples/ (intentional fixtures).
    """
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_raw = (isinstance(ret, ast.Name) and ret.id in {"dict", "Dict", "Mapping"}) or (
            isinstance(ret, ast.Subscript) and isinstance(ret.value, ast.Name) and ret.value.id in {"dict", "Dict", "Mapping"}
        )
        if is_raw and not suppressed(noqa, A2K011, node.lineno):
            yield msg(
                A2K011,
                filename,
                node,
                f"tool {node.name!r} returns raw dict/Mapping; prefer a Pydantic BaseModel for richer schema snapshots",
            )


__all__ = ["rule_a2k002", "rule_a2k003", "rule_a2k011"]
