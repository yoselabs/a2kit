"""Capability-string rules.

- A2K009 — raw built-in capability strings.
- A2K012 — raw custom capability strings (require ``Final[str]`` constants).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules import iter_string_literals
from a2kit.packages.lint.static import (
    A2K009,
    A2K012,
    BUILTIN_CAPS,
    LintMessage,
    _msg,
    is_fixture_path,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REEXPORT_CACHE: dict[tuple[str, str, str], bool] = {}


def _reset_reexport_cache() -> None:
    _REEXPORT_CACHE.clear()


def _module_to_path(module_name: str, project_root: Path) -> Path | None:
    parts = module_name.split(".")
    pkg_init = project_root.joinpath(*parts) / "__init__.py"
    if pkg_init.is_file():
        return pkg_init
    mod_py = project_root.joinpath(*parts).with_suffix(".py")
    if mod_py.is_file():
        return mod_py
    return None


def _has_final_str_assign(tree: ast.AST, name: str) -> bool:
    if not isinstance(tree, ast.Module):
        return False
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        if stmt.target.id != name:
            continue
        anno = stmt.annotation
        if not isinstance(anno, ast.Subscript):
            continue
        base = anno.value
        base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
        if base_name != "Final":
            continue
        slice_node = anno.slice
        if isinstance(slice_node, ast.Name) and slice_node.id == "str":
            return True
    return False


def _find_reexport(tree: ast.AST, name: str) -> str | None:
    if not isinstance(tree, ast.Module):
        return None
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom) or stmt.module is None:
            continue
        for alias in stmt.names:
            local = alias.asname or alias.name
            if local == name:
                return stmt.module
    return None


def _resolve_through_reexports(
    module_name: str,
    attr_name: str,
    project_root: Path,
    *,
    max_depth: int = 3,
) -> bool:
    cache_key = (str(project_root), module_name, attr_name)
    if cache_key in _REEXPORT_CACHE:
        return _REEXPORT_CACHE[cache_key]
    seen: set[str] = set()
    current_module = module_name
    for _ in range(max_depth):
        if current_module in seen:
            break
        seen.add(current_module)
        path = _module_to_path(current_module, project_root)
        if path is None:
            break
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            break
        if _has_final_str_assign(tree, attr_name):
            _REEXPORT_CACHE[cache_key] = True
            return True
        next_module = _find_reexport(tree, attr_name)
        if next_module is None:
            break
        current_module = next_module
    _REEXPORT_CACHE[cache_key] = False
    return False


def _find_project_root(filename: str) -> Path | None:
    cur = Path(filename).resolve().parent
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def _collect_imported_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def _collect_import_sources_local(tree: ast.AST) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for alias in node.names:
                local = alias.asname or alias.name
                out[local] = (node.module, alias.name)
    return out


def _collect_local_final_str_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    if not isinstance(tree, ast.Module):
        return out
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        anno = stmt.annotation
        if not isinstance(anno, ast.Subscript):
            continue
        base = anno.value
        base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
        if base_name != "Final":
            continue
        slice_node = anno.slice
        if isinstance(slice_node, ast.Name) and slice_node.id == "str":
            out.add(stmt.target.id)
    return out


def _collect_safe_capability_names(tree: ast.AST, filename: str) -> set[str]:
    imported = _collect_imported_names(tree)
    import_sources = _collect_import_sources_local(tree)
    local_finals = _collect_local_final_str_names(tree)
    project_root = _find_project_root(filename)
    safe_names = local_finals.copy()
    for name in imported:
        if name in safe_names:
            continue
        module, attr = import_sources[name]
        if project_root is None or _resolve_through_reexports(module, attr, project_root):
            safe_names.add(name)
    return safe_names


def _iter_capability_kwarg_containers(tree: ast.AST) -> Iterable[ast.Set | ast.List | ast.Tuple]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            if isinstance(kw.value, (ast.Set, ast.List, ast.Tuple)):
                yield kw.value


def rule_a2k009(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            for raw in iter_string_literals(kw.value):
                value = raw.value
                if not isinstance(value, str):
                    continue
                if value in BUILTIN_CAPS and not suppressed(noqa, A2K009, raw.lineno):
                    suggestion = f"Cap.{value.upper()}"
                    yield _msg(
                        A2K009,
                        filename,
                        raw,
                        f"raw built-in capability string {value!r}; prefer {suggestion}",
                    )


def rule_a2k012(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    safe_names = _collect_safe_capability_names(tree, filename)
    for container in _iter_capability_kwarg_containers(tree):
        for elt in container.elts:
            if isinstance(elt, ast.Name) and elt.id in safe_names:
                continue
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                continue
            value = elt.value
            if value in BUILTIN_CAPS or suppressed(noqa, A2K012, elt.lineno):
                continue
            yield _msg(
                A2K012,
                filename,
                elt,
                f"raw custom capability {value!r}; define as `Final[str]` constant for type safety",
            )


__all__ = ["rule_a2k009", "rule_a2k012"]
