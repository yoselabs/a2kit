from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class LintMessage:
    rule_id: str
    severity: Severity
    path: Path
    line: int
    col: int
    message: str

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.rule_id} [{self.severity}] {self.message}"


# Heuristic: any Raises(arg) where arg's dotted prefix matches one of these
# is treated as a non-AppError marker. v1 lint is static-only; runtime
# import-and-issubclass would defeat the no-coupling design.
KNOWN_EXTERNAL_PREFIXES: frozenset[str] = frozenset({"httpx", "asyncpg", "redis", "sqlalchemy", "fastapi", "starlette"})


# Tool decorators that mark a function as a typed-error boundary. Includes
# the a2kit verb decorators and the generic enricher/tool decorators.
TOOL_DECORATOR_TAILS: frozenset[str] = frozenset({"read", "write", "list_", "tool", "api", "mcp"})


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        if prefix is None:
            return None
        return f"{prefix}.{node.attr}"
    return None


def is_tool_decorator(decorator: ast.expr) -> bool:
    target = decorator
    if isinstance(target, ast.Call):
        target = target.func
    name = dotted_name(target)
    if name is None:
        return False
    tail = name.rsplit(".", 1)[-1]
    return tail in TOOL_DECORATOR_TAILS


def find_annotated_raises(annotation: ast.expr | None) -> list[ast.expr]:
    """Return the list of type argument AST nodes inside any Raises(...) marker
    appearing in an Annotated[T, Raises(...), ...] expression."""
    if annotation is None:
        return []
    results: list[ast.expr] = []
    if not isinstance(annotation, ast.Subscript):
        return results
    name = dotted_name(annotation.value)
    if name is None or name.rsplit(".", 1)[-1] != "Annotated":
        return results
    slice_node = annotation.slice
    elements: list[ast.expr]
    if isinstance(slice_node, ast.Tuple):
        elements = list(slice_node.elts)
    else:
        elements = [slice_node]
    for el in elements:
        if isinstance(el, ast.Call):
            call_name = dotted_name(el.func)
            if call_name is not None and call_name.rsplit(".", 1)[-1] == "Raises":
                results.extend(el.args)
    return results


def collect_raises_names(annotation: ast.expr | None) -> set[str]:
    """Return the set of dotted names declared in Raises(...) markers."""
    return {n for arg in find_annotated_raises(annotation) if (n := dotted_name(arg)) is not None}


def is_tool_function(node: ast.AST) -> bool:
    if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return False
    return any(is_tool_decorator(dec) for dec in node.decorator_list)


def iter_functions(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
