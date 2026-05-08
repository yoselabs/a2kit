"""Rules that inspect the `capabilities=` kwarg.

A2K009 — Raw built-in capability string (`'write'` instead of `Cap.WRITE`).
A2K012 — Raw custom capability string (advisory; lift into `Final[str]` constant).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import resolve_through_reexports
from a2kit.lint._common import (
    A2K009,
    A2K012,
    BUILTIN_CAPS,
    is_fixture_path,
    msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.lint._common import LintMessage


def _iter_string_literals(node: ast.expr) -> Iterable[ast.Constant]:
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                yield elt


def rule_a2k009(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K009 — Raw built-in capability string (`'write'` instead of `Cap.WRITE`)."""
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            for raw in _iter_string_literals(kw.value):
                value = raw.value
                if not isinstance(value, str):  # pragma: no cover — _iter_string_literals filters
                    continue
                if value in BUILTIN_CAPS and not suppressed(noqa, A2K009, raw.lineno):
                    suggestion = f"Cap.{value.upper()}"
                    yield msg(
                        A2K009,
                        filename,
                        raw,
                        f"raw built-in capability string {value!r}; prefer {suggestion}",
                    )


def _collect_imported_names(tree: ast.AST) -> set[str]:
    """Return the set of names brought into the module via `from x import a, b`."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def _collect_import_sources(tree: ast.AST) -> dict[str, tuple[str, str]]:
    """Map local-name -> (module, original-attr) for each `from MODULE import NAME [as LOCAL]`.

    Used by A2K012 v0.7 re-export resolution.
    """
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local = alias.asname or alias.name
                out[local] = (node.module, alias.name)
    return out


def _find_project_root(filename: str) -> Path | None:
    """Walk up from `filename` to find the nearest pyproject.toml's parent."""
    cur = Path(filename).resolve().parent
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _collect_local_final_str_names(tree: ast.AST) -> set[str]:
    """Return module-level names annotated as `Final[str]`."""
    out: set[str] = set()
    if not isinstance(tree, ast.Module):  # pragma: no cover — driver always passes Module
        return out
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        anno = stmt.annotation
        is_final_str = False
        if isinstance(anno, ast.Subscript):
            base = anno.value
            base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
            if base_name == "Final":
                slice_node = anno.slice
                if isinstance(slice_node, ast.Name) and slice_node.id == "str":
                    is_final_str = True
        if is_final_str:
            out.add(stmt.target.id)
    return out


def _collect_safe_capability_names(tree: ast.AST, filename: str) -> set[str]:
    """Names that resolve to Final[str] constants — locally or via re-exports."""
    imported = _collect_imported_names(tree)
    import_sources = _collect_import_sources(tree)
    local_finals = _collect_local_final_str_names(tree)
    project_root = _find_project_root(filename)
    safe_names = local_finals.copy()
    for name in imported:
        if name in safe_names:  # pragma: no cover — local_finals + ImportFrom rarely overlap
            continue
        module, attr = import_sources[name]
        if project_root is None or resolve_through_reexports(module, attr, project_root):
            safe_names.add(name)
    return safe_names


def _iter_capability_kwarg_containers(tree: ast.AST) -> Iterable[ast.Set | ast.List | ast.Tuple]:
    """Yield each `capabilities=<container>` value where container is Set/List/Tuple."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            if isinstance(kw.value, (ast.Set, ast.List, ast.Tuple)):
                yield kw.value


def _check_capability_element(
    elt: ast.expr,
    safe_names: set[str],
    noqa: dict,
    filename: str,
) -> Iterable[LintMessage]:
    """Yield A2K012 for one element of a `capabilities=` container, if it qualifies."""
    if isinstance(elt, ast.Name) and elt.id in safe_names:
        return
    if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
        return
    value = elt.value
    if value in BUILTIN_CAPS or suppressed(noqa, A2K012, elt.lineno):
        return
    yield msg(
        A2K012,
        filename,
        elt,
        f"raw custom capability {value!r}; define as `Final[str]` constant for type safety",
    )


def rule_a2k012(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K012 — Custom capability used as raw string.

    Advisory: a literal string in `capabilities={...}` that is NOT a built-in
    Cap.* constant AND NOT a referenced `Final[str]` constant should be lifted
    into a constants module for type safety.
    """
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    safe_names = _collect_safe_capability_names(tree, filename)
    for container in _iter_capability_kwarg_containers(tree):
        for elt in container.elts:
            yield from _check_capability_element(elt, safe_names, noqa, filename)


__all__ = ["rule_a2k009", "rule_a2k012"]
