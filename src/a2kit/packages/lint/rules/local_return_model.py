"""A2K-LOCAL-RETURN-MODEL — tool return types must be module-scope BaseModels.

Mirrors ``A2K-LDD-REPORT-TYPE``'s logic for the return-annotation site. FastMCP's
``inspect.signature(eval_str=True)`` walks the wrapper chain and runs
``eval(annotation_str, globals, locals)`` against the module's globals — names
defined inside a function (``__qualname__`` contains ``<locals>``) are not
reachable, producing ``InvalidSignature`` at server-build time. The error is
opaque, so we surface it pre-run.

Rule code: ``A2K-LOCAL-RETURN-MODEL``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules.detect import is_a2kit_tool_decorator as _is_a2kit_verb_decorator

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage


from a2kit.packages.lint.rules._ast_helpers import is_basemodel_base as _is_basemodel_base


def _is_basemodel_classdef(cls: ast.ClassDef) -> bool:
    return any(_is_basemodel_base(b) for b in cls.bases)


def _is_type_checking_block(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _collect_basemodel_classes(
    tree: ast.Module,
) -> tuple[dict[str, ast.ClassDef], set[str]]:
    """Walk the tree; return ``(non_module_scope, module_scope_names)``.

    ``non_module_scope`` maps name → ClassDef for ``BaseModel`` subclasses defined
    inside any function, classmethod, or closure (but NOT inside ``if TYPE_CHECKING:``).
    ``module_scope_names`` is the set of ``BaseModel`` subclass names at module top-level
    (these are always OK and short-circuit the check).
    """
    module_scope: set[str] = set()
    nested: dict[str, ast.ClassDef] = {}

    # Module-scope BaseModel classes (top-level only).
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and _is_basemodel_classdef(node):
            module_scope.add(node.name)

    # Nested BaseModel classes — anywhere except top-level and TYPE_CHECKING blocks.
    def _walk(node: ast.AST, in_function: bool, in_type_checking: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and _is_type_checking_block(child):
                _walk(child, in_function, in_type_checking=True)
                continue
            if isinstance(child, ast.ClassDef) and _is_basemodel_classdef(child) and in_function and not in_type_checking:
                nested[child.name] = child
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _walk(child, in_function=True, in_type_checking=in_type_checking)
            else:
                _walk(child, in_function, in_type_checking)

    _walk(tree, in_function=False, in_type_checking=False)
    return nested, module_scope


def _annotation_root_names(ann: ast.expr) -> Iterable[ast.Name]:
    """Yield every ``Name`` reachable from a return annotation, peeling generics.

    Walks ``Name``, ``Subscript`` (recurses into ``slice``), and ``Tuple`` (recurses
    into ``elts``). ``Attribute`` (e.g. ``otherpkg.Result``) is intentionally
    skipped — out of jurisdiction (cross-module) per the rule's scope.
    """
    if isinstance(ann, ast.Name):
        yield ann
        return
    if isinstance(ann, ast.Subscript):
        # Generic carrier name (e.g. ``Page`` in ``Page[Result]``)
        yield from _annotation_root_names(ann.value)
        yield from _annotation_root_names(ann.slice)
        return
    if isinstance(ann, ast.Tuple):
        for elt in ann.elts:
            yield from _annotation_root_names(elt)
        return
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        # PEP 604 unions: ``X | Y``
        yield from _annotation_root_names(ann.left)
        yield from _annotation_root_names(ann.right)
        return


def _iter_tool_functions(tree: ast.Module) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_is_a2kit_verb_decorator(d) for d in node.decorator_list):
            yield node


def rule_local_return_model(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    from a2kit.packages.lint.static import (
        A2K_LOCAL_RETURN_MODEL,
        LintMessage,
        parse_noqa,
        suppressed,
    )

    if not isinstance(tree, ast.Module):
        return
    nested, module_scope = _collect_basemodel_classes(tree)
    if not nested:
        return  # nothing to flag in this module

    noqa = parse_noqa(source)
    for fn in _iter_tool_functions(tree):
        if fn.returns is None:
            continue
        for name_node in _annotation_root_names(fn.returns):
            ident = name_node.id
            if ident in module_scope:
                continue
            if ident not in nested:
                continue
            if suppressed(noqa, A2K_LOCAL_RETURN_MODEL, name_node.lineno):
                continue
            yield LintMessage(
                rule=A2K_LOCAL_RETURN_MODEL,
                filename=filename,
                line=name_node.lineno,
                col=name_node.col_offset,
                message=(
                    f"return annotation references {ident!r}, a `BaseModel` defined inside "
                    "a function/method/closure. FastMCP's signature.eval_str=True cannot "
                    "resolve names from a function that has already returned. Hoist the "
                    "class to module scope."
                ),
            )


__all__ = ["rule_local_return_model"]
