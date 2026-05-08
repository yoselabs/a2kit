"""Rules that inspect tool docstrings.

A2K006 — same param description in 3+ tools (cross-file; suggests
         `register_param_doc`).
A2K013 — manual `connection_param_doc` / `param_doc` f-string in docstring
         (auto-injection covers it).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import is_tool_function
from a2kit.lint._common import (
    A2K006,
    A2K013,
    LintMessage,
    is_fixture_path,
    msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


_A2K013_MARKERS = ("a2kit.docs.connection_param_doc(", "a2kit.docs.param_doc(")


def collect_param_descriptions(tree: ast.AST) -> dict[str, list[str]]:
    """Pull `name: description` lines from each tool's docstring.

    Used by the cross-file A2K006 driver — descriptions repeated across many
    tools are candidates for `a2kit.docs.register_param_doc`.
    """
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        doc = ast.get_docstring(node) or ""
        for raw in doc.splitlines():
            line = raw.strip()
            if ":" not in line:
                continue
            name, _, text = line.partition(":")
            name = name.strip()
            text = text.strip()
            if not name.isidentifier() or len(text) < 20:
                continue
            out.setdefault(name, []).append(text)
    return out


def rule_a2k006_cross(per_file: dict[str, dict[str, list[str]]]) -> Iterable[LintMessage]:
    flat: dict[tuple[str, str], list[str]] = {}
    for filename, mapping in per_file.items():
        for name, texts in mapping.items():
            for t in texts:
                flat.setdefault((name, t), []).append(filename)
    for (name, _t), files in flat.items():
        if len(files) >= 3:
            yield LintMessage(
                rule=A2K006,
                filename=files[0],
                line=1,
                col=0,
                message=(f"param {name!r} has the same description in {len(files)} tools; consider a2kit.docs.register_param_doc"),
            )


def _first_doc_text(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return raw text of the first body stmt if it's a string-or-f-string expression."""
    if not fn.body:
        return ""  # pragma: no cover — fn body always present
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
            elif isinstance(piece, ast.FormattedValue):  # pragma: no branch
                out.append(ast.unparse(piece.value))
        return "".join(out)
    return ""  # pragma: no cover — first stmt is non-string expression


def rule_a2k013(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K013 — Manual param-doc f-string in a tool docstring.

    Auto-injection (v0.7) prepends canonical text at decoration time. A docstring
    that still calls `a2kit.docs.connection_param_doc(...)` / `a2kit.docs.param_doc(...)`
    via f-string is redundant.
    """
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
        yield msg(
            A2K013,
            filename,
            node,
            f"tool {node.name!r}: docstring calls a2kit.docs.connection_param_doc/param_doc; auto-injection (v0.7) covers it.",
        )


__all__ = [
    "collect_param_descriptions",
    "rule_a2k006_cross",
    "rule_a2k013",
]
