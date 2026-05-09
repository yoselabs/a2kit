"""DI-family rules.

- A2K-DI-ANNOTATED — ``Annotated[T, Depends(fn)]`` in tool params.
- A2K-DI-IMPORT-LEGACY — ``from a2kit.di import Depends``.
- A2K-DI-IMPORT-SLOW — ``from fastmcp.dependencies import Depends``.
- A2K-DI-KWONLY — DI param not behind ``*,``.
- A2K-DI-PYDANTIC-VALIDATE — ``pydantic.validate_call`` over Depends-fn.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules import collect_import_sources, is_tool_function
from a2kit.packages.lint.static import (
    A2K_DI_ANNOTATED,
    A2K_DI_IMPORT_LEGACY,
    A2K_DI_IMPORT_SLOW,
    A2K_DI_KWONLY,
    A2K_DI_PYDANTIC_VALIDATE,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def _annotated_subscript_has_depends(slice_node: ast.expr) -> bool:
    elts: list[ast.expr]
    if isinstance(slice_node, ast.Tuple):
        elts = list(slice_node.elts)
    else:
        elts = [slice_node]
    for e in elts:
        if isinstance(e, ast.Call):
            f = e.func
            if isinstance(f, ast.Name) and f.id == "Depends":
                return True
            if isinstance(f, ast.Attribute) and f.attr == "Depends":
                return True
    return False


def _is_annotated_with_depends(annotation: ast.expr | None) -> bool:
    if not isinstance(annotation, ast.Subscript):
        return False
    base = annotation.value
    base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
    if base_name != "Annotated":
        return False
    return _annotated_subscript_has_depends(annotation.slice)


def _is_depends_default(default: ast.expr | None) -> bool:
    if not isinstance(default, ast.Call):
        return False
    f = default.func
    if isinstance(f, ast.Name) and f.id == "Depends":
        return True
    return bool(isinstance(f, ast.Attribute) and f.attr == "Depends")


def _function_has_depends_default(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    args = fn.args
    if any(_is_depends_default(d) for d in args.defaults):
        return True
    return bool(any(d is not None and _is_depends_default(d) for d in args.kw_defaults))


def _function_def_at(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _is_validate_call(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Attribute) and f.attr == "validate_call" and isinstance(f.value, ast.Name) and f.value.id == "pydantic":
        return True
    return bool(isinstance(f, ast.Name) and f.id == "validate_call")


def rule_di_annotated(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        params = list(node.args.args) + list(node.args.kwonlyargs) + list(node.args.posonlyargs)
        for p in params:
            if _is_annotated_with_depends(p.annotation) and not suppressed(noqa, A2K_DI_ANNOTATED, p.lineno):
                yield _msg(
                    A2K_DI_ANNOTATED,
                    filename,
                    p,
                    (
                        f"parameter {p.arg!r}: use parameter-default form `T = Depends(fn)` instead of "
                        "`Annotated[T, Depends(fn)]`. The Annotated form is for type metadata, not value injection."
                    ),
                )


def rule_di_import_legacy(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "a2kit.di":
            continue
        if not any(alias.name == "Depends" for alias in node.names):
            continue
        if suppressed(noqa, A2K_DI_IMPORT_LEGACY, node.lineno):
            continue
        yield _msg(
            A2K_DI_IMPORT_LEGACY,
            filename,
            node,
            "migrate to `from uncalled_for import Depends`. a2kit.di is removed in v1.0.",
        )


def rule_di_import_slow(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module != "fastmcp.dependencies":
            continue
        if not any(alias.name == "Depends" for alias in node.names):
            continue
        if suppressed(noqa, A2K_DI_IMPORT_SLOW, node.lineno):
            continue
        yield _msg(
            A2K_DI_IMPORT_SLOW,
            filename,
            node,
            ("use `from uncalled_for import Depends`. The fastmcp path eagerly loads fastmcp, hurting cold-start."),
        )


def rule_di_kwonly(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        positional = list(node.args.posonlyargs) + list(node.args.args)
        defaults = list(node.args.defaults)
        if not defaults:
            continue
        offset = len(positional) - len(defaults)
        for i, default in enumerate(defaults):
            if not _is_depends_default(default):
                continue
            arg = positional[offset + i] if 0 <= offset + i < len(positional) else None
            target = arg if arg is not None else node
            line = getattr(target, "lineno", node.lineno)
            if suppressed(noqa, A2K_DI_KWONLY, line):
                continue
            arg_name = arg.arg if arg is not None else "<unknown>"
            yield _msg(
                A2K_DI_KWONLY,
                filename,
                target,
                (
                    f"DI parameter {arg_name!r} on tool {node.name!r} is positional. "
                    "DI parameters must be keyword-only — add `*,` before the first DI parameter."
                ),
            )


def rule_di_pydantic_validate(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    imports = collect_import_sources(tree)
    src = imports.get("validate_call")
    pydantic_bare_validate_call = src is not None and src[0] == "pydantic"

    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_validate_call(node):
            continue
        f = node.func
        if isinstance(f, ast.Name) and not pydantic_bare_validate_call:
            continue
        if not node.args:
            continue
        target_arg = node.args[0]
        target_fn: ast.FunctionDef | ast.AsyncFunctionDef | None = None
        if isinstance(target_arg, ast.Name):
            target_fn = _function_def_at(tree, target_arg.id)
        if target_fn is None or not _function_has_depends_default(target_fn):
            continue
        if suppressed(noqa, A2K_DI_PYDANTIC_VALIDATE, node.lineno):
            continue
        yield _msg(
            A2K_DI_PYDANTIC_VALIDATE,
            filename,
            node,
            (
                f"`validate_call` wraps {target_fn.name!r} which has Depends defaults. "
                "Always run `without_dependencies(fn)` before pydantic validation; "
                "otherwise the Depends sentinel leaks as the parameter value."
            ),
        )


__all__ = [
    "rule_di_annotated",
    "rule_di_import_legacy",
    "rule_di_import_slow",
    "rule_di_kwonly",
    "rule_di_pydantic_validate",
]
