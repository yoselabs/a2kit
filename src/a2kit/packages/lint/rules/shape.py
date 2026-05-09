"""Return-annotation + docstring shape rules.

- A2K002: tool declares ``-> str`` (FastMCP double-serialises).
- A2K003: tool returns module-local Pydantic model.
- A2K011: tool returns raw dict / Mapping.
- A2K013: tool docstring calls ``a2kit.docs.connection_param_doc/param_doc``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules import is_tool_function
from a2kit.packages.lint.static import (
    A2K002,
    A2K003,
    A2K011,
    A2K013,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_A2K013_MARKERS = ("a2kit.docs.connection_param_doc(", "a2kit.docs.param_doc(")


def _local_pydantic_classes(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    if not isinstance(tree, ast.Module):
        return found
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            base_name = base.attr if isinstance(base, ast.Attribute) else (base.id if isinstance(base, ast.Name) else None)
            if base_name in {"BaseModel", "ConnectionConfig"}:
                found.add(node.name)
                break
    return found


def _first_doc_text(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    if not fn.body:
        return ""
    first = fn.body[0]
    if not isinstance(first, ast.Expr):
        return ""
    val = first.value
    if isinstance(val, ast.Constant) and isinstance(val.value, str):
        return val.value
    if isinstance(val, ast.JoinedStr):
        out: list[str] = []
        for piece in val.values:
            if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                out.append(piece.value)
            elif isinstance(piece, ast.FormattedValue):
                out.append(ast.unparse(piece.value))
        return "".join(out)
    return ""


def rule_a2k002(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_str = (isinstance(ret, ast.Name) and ret.id == "str") or (isinstance(ret, ast.Constant) and ret.value == "str")
        if is_str and not suppressed(noqa, A2K002, node.lineno):
            yield _msg(A2K002, filename, node, f"tool {node.name!r} declares `-> str`; FastMCP double-serialises")


def rule_a2k003(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    locals_ = _local_pydantic_classes(tree)
    if not locals_:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret_name = node.returns.id if isinstance(node.returns, ast.Name) else None
        if ret_name in locals_ and not suppressed(noqa, A2K003, node.lineno):
            yield _msg(A2K003, filename, node, f"tool {node.name!r} returns module-local Pydantic model {ret_name!r}")


def rule_a2k011(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
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
            yield _msg(
                A2K011,
                filename,
                node,
                f"tool {node.name!r} returns raw dict/Mapping; prefer a Pydantic BaseModel for richer schema snapshots",
            )


def rule_a2k013(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        text = _first_doc_text(node)
        if not any(m in text for m in _A2K013_MARKERS):
            continue
        if suppressed(noqa, A2K013, node.lineno):
            continue
        yield _msg(
            A2K013,
            filename,
            node,
            f"tool {node.name!r}: docstring calls a2kit.docs.connection_param_doc/param_doc; auto-injection covers it.",
        )


__all__ = ["rule_a2k002", "rule_a2k003", "rule_a2k011", "rule_a2k013"]
