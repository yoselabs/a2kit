from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2effect._lint._core import KNOWN_EXTERNAL_PREFIXES, LintMessage, dotted_name, find_annotated_raises

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def raises_not_typed_rule(tree: ast.Module, *, path: Path, source: str = "") -> Iterator[LintMessage]:
    for node in ast.walk(tree):
        annotation: ast.expr | None
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            annotation = node.returns
        elif isinstance(node, ast.AnnAssign | ast.arg):
            annotation = node.annotation
        else:
            continue
        for arg in find_annotated_raises(annotation):
            name = dotted_name(arg)
            if name is None:
                continue
            prefix = name.split(".", 1)[0]
            if prefix in KNOWN_EXTERNAL_PREFIXES:
                yield LintMessage(
                    rule_id="A2K-RAISES-NOT-TYPED",
                    severity="error",
                    path=path,
                    line=arg.lineno,
                    col=arg.col_offset,
                    message=(
                        f"Raises({name}) member is not an AppError subclass; "
                        f"subclass a2effect.AppError or register an enricher / raises_as mapping"
                    ),
                )
