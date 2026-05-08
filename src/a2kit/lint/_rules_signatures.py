"""Rules that inspect tool function signatures.

A2K001 — `connection_param='X'` requires param X on the function.
A2K004 — Tool with `connection` param should reference `connection_param_doc`.
A2K005 — Leftover `KEY_FIELDS` migration aid + tool-param compat against
         `cls.Key` arity (single-string param insufficient for multi-field keys).
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import (
    connection_info_key_class,
    connection_info_subclasses,
    decorator_kwargs,
    function_has_param,
    is_a2kit_tool_decorator,
    is_tool_function,
    key_fields_value,
    namedtuple_field_count,
)
from a2kit.lint._common import (
    A2K001,
    A2K004,
    A2K005,
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


def _check_legacy_key_fields(cls: ast.ClassDef, filename: str, noqa: dict) -> Iterable[LintMessage]:
    """v0.5: any leftover `KEY_FIELDS = ...` is a migration error."""
    kf = key_fields_value(cls)
    if kf is None:
        return
    if suppressed(noqa, A2K005, cls.lineno):
        return
    yield msg(
        A2K005,
        filename,
        cls,
        f"{cls.name}.KEY_FIELDS is a v0.4 legacy attribute removed in v0.5; "
        f"declare a NamedTuple and pass `class {cls.name}(ConnectionInfo, key=YourKey)` instead",
    )


def _arity_by_connection_class(tree: ast.AST) -> dict[str, int]:
    """Map ConnectionInfo subclass name → arity of its declared Key NamedTuple."""
    arity: dict[str, int] = {}
    for cls in connection_info_subclasses(tree):
        key_name = connection_info_key_class(cls)
        if key_name is None:
            arity[cls.name] = 1
            continue
        count = namedtuple_field_count(tree, key_name)
        if count is not None:
            arity[cls.name] = count
    return arity


def _assignment_targets_and_value(stmt: ast.stmt) -> tuple[list[ast.expr], ast.expr | None]:
    """Normalise Assign/AnnAssign into (targets, value); ([], None) for other stmts."""
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets), stmt.value
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return [stmt.target], stmt.value
    return [], None


def _connection_store_class_arg(value: ast.expr) -> str | None:
    """If `value` is `ConnectionStore(..., Cls)`, return `Cls`'s name; else None."""
    if not isinstance(value, ast.Call):
        return None
    callee = value.func
    callee_name = callee.id if isinstance(callee, ast.Name) else (callee.attr if isinstance(callee, ast.Attribute) else None)
    if callee_name != "ConnectionStore" or not value.args:
        return None
    cls_arg = value.args[-1]
    return cls_arg.id if isinstance(cls_arg, ast.Name) else None


def _store_var_to_arity(tree: ast.AST) -> dict[str, int]:
    """Best-effort: map module-local variable name → arity of its store's `cls.Key`."""
    arity_by_class = _arity_by_connection_class(tree)
    if not arity_by_class or not isinstance(tree, ast.Module):
        return {}

    out: dict[str, int] = {}
    for stmt in tree.body:
        targets, value = _assignment_targets_and_value(stmt)
        if value is None:
            continue
        cls_name = _connection_store_class_arg(value)
        if cls_name is None or cls_name not in arity_by_class:  # pragma: no cover — alt forms
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name):  # pragma: no branch — non-Name targets fall through
                out[tgt.id] = arity_by_class[cls_name]
    return out


def _annotation_acceptable_for_arity(anno: ast.expr | None, arity: int) -> bool | None:
    """Return True/False, or None if the annotation is unresolvable / opaque."""
    if anno is None:
        return None
    if arity == 1:
        # Single-field key: any annotation (including bare `str`) is acceptable.
        return True
    if isinstance(anno, ast.Name):
        # Multi-field key: bare `str` is the one shape we reject.
        return anno.id != "str"
    if isinstance(anno, ast.Subscript):
        # tuple[...]/dict[...]/etc. — any subscripted shape is accepted.
        return True
    return None  # pragma: no cover — opaque annotation


def _find_param_annotation(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> ast.expr | None:
    args = list(fn.args.args) + list(fn.args.kwonlyargs) + list(fn.args.posonlyargs)
    for a in args:
        if a.arg == name:
            return a.annotation
    return None  # pragma: no cover — A2K001 catches the missing-param case


def _scan_a2k005_tool_calls(tree: ast.AST, filename: str, source: str, store_arity: dict[str, int]) -> Iterable[LintMessage]:
    """Walk @a2kit.tool decorations for connection_param arity mismatches."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not is_a2kit_tool_decorator(dec):
                continue
            kw = decorator_kwargs(dec)
            store_arg = kw.get("store")
            cp = kw.get("connection_param")
            if not isinstance(store_arg, ast.Name) or not isinstance(cp, ast.Constant) or not isinstance(cp.value, str):
                continue
            arity = store_arity.get(store_arg.id)
            if arity is None:
                if not suppressed(noqa, A2K005, node.lineno):
                    yield msg(
                        A2K005,
                        filename,
                        node,
                        f"could not resolve store {store_arg.id!r}; check `{cp.value}` arity manually",
                    )
                continue
            param_anno = _find_param_annotation(node, cp.value)
            verdict = _annotation_acceptable_for_arity(param_anno, arity)
            if verdict is False and not suppressed(noqa, A2K005, node.lineno):
                yield msg(
                    A2K005,
                    filename,
                    node,
                    f"tool {node.name!r}: {cp.value}: str is insufficient for cls.Key arity {arity}; "
                    "use the NamedTuple key class, tuple[str, ...], or dict[str, str]",
                )


def rule_a2k005(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K005 — leftover `KEY_FIELDS` migration aid + tool-param compat against `cls.Key` arity (v0.5)."""
    noqa = parse_noqa(source)
    for cls in connection_info_subclasses(tree):
        yield from _check_legacy_key_fields(cls, filename, noqa)
    if is_fixture_path(filename):
        return
    store_arity = _store_var_to_arity(tree)
    yield from _scan_a2k005_tool_calls(tree, filename, source, store_arity)


__all__ = ["rule_a2k001", "rule_a2k004", "rule_a2k005"]
