from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2effect._lint._core import LintMessage, collect_raises_names, dotted_name, is_tool_function, iter_functions

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _is_inside_handler_that_translates(raise_node: ast.Raise, fn: ast.FunctionDef | ast.AsyncFunctionDef, declared: set[str]) -> bool:
    """A `raise X(...)` inside an `except` handler is considered translation-safe
    when X is one of the declared raises (the handler is rewriting an
    untranslated underlying error into a declared one)."""
    if raise_node.exc is None:
        return True  # bare re-raise
    name = dotted_name(raise_node.exc.func) if isinstance(raise_node.exc, ast.Call) else dotted_name(raise_node.exc)
    if name is None:
        return False
    return _matches_declared(name, declared)


def _matches_declared(name: str, declared: set[str]) -> bool:
    tail = name.rsplit(".", 1)[-1]
    return name in declared or tail in {d.rsplit(".", 1)[-1] for d in declared}


def raises_closure_rule(tree: ast.Module, *, path: Path, source: str = "") -> Iterator[LintMessage]:
    for fn in iter_functions(tree):
        if not is_tool_function(fn):
            continue
        declared = collect_raises_names(fn.returns)
        if not declared:
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.Raise):
                continue
            if node.exc is None:
                continue  # bare re-raise is fine
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            name = dotted_name(target)
            if name is None:
                continue
            if _matches_declared(name, declared):
                continue
            yield LintMessage(
                rule_id="A2K-RAISES-CLOSURE",
                severity="error",
                path=path,
                line=node.lineno,
                col=node.col_offset,
                message=(
                    f"raise {name}(...) not covered by declared Raises({', '.join(sorted(declared))}); "
                    f"add {name} to the return annotation's Raises(...), translate via raises_as, "
                    f"or wrap in try/except that re-raises a declared type"
                ),
            )
