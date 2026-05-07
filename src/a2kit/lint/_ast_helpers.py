"""AST helpers shared by static lint rules — no rule logic, just walkers."""

from __future__ import annotations

import ast
from pathlib import Path  # noqa: TC003 — runtime-needed for `is_file()` calls in re-export resolution
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from collections.abc import Iterable


def is_a2kit_tool_decorator(dec: ast.expr) -> bool:
    """True if decorator looks like `@a2kit.tool(...)` / `@a2kit.tools.tool(...)` / `@tool(...)`."""
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    if isinstance(target, ast.Attribute):
        return target.attr == "tool" and isinstance(target.value, ast.Name) and target.value.id in {"a2kit", "tools"}
    if isinstance(target, ast.Name):
        return target.id == "tool"
    return False


def decorator_kwargs(dec: ast.expr) -> dict[str, ast.expr]:
    """Return `{name: value}` for keyword args in a decorator call."""
    if not isinstance(dec, ast.Call):
        return {}
    return {kw.arg: kw.value for kw in dec.keywords if kw.arg is not None}


def is_server_tool_decorator(dec: ast.expr) -> bool:
    """`@server.tool()` style — any `*.tool(...)` attribute call."""
    call = dec if isinstance(dec, ast.Call) else None
    target = call.func if call else dec
    return isinstance(target, ast.Attribute) and target.attr == "tool"


def is_tool_function(node: ast.AST) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """True if `node` is a function decorated with a tool decorator.

    Returns a `TypeGuard` so type-checkers narrow callers from `ast.AST` to
    `FunctionDef | AsyncFunctionDef`, exposing `.returns`, `.lineno`, `.name`.
    """
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(is_a2kit_tool_decorator(d) or is_server_tool_decorator(d) for d in node.decorator_list)


def function_has_param(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    args = fn.args
    all_args = list(args.args) + list(args.kwonlyargs) + list(args.posonlyargs)
    return any(a.arg == name for a in all_args)


def connection_info_subclasses(tree: ast.AST) -> Iterable[ast.ClassDef]:
    """Yield top-level class defs that subclass a `ConnectionInfo`-named base."""
    if not isinstance(tree, ast.Module):
        return
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            base_name: str | None = None
            if isinstance(base, ast.Attribute):
                base_name = base.attr
            elif isinstance(base, ast.Name):
                base_name = base.id
            if base_name == "ConnectionInfo":
                yield node
                break


def key_fields_value(cls: ast.ClassDef) -> ast.expr | None:
    """Return the AST value of `KEY_FIELDS = ...` on this class, or None.

    v0.5: legacy attribute. Lint A2K005 emits a migration error when this is
    found; the helper itself just locates the assignment.
    """
    for stmt in cls.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(stmt, ast.Assign):
            targets = list(stmt.targets)
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value = stmt.value
        for t in targets:
            if isinstance(t, ast.Name) and t.id == "KEY_FIELDS" and value is not None:
                return value
    return None


def connection_info_key_class(cls: ast.ClassDef) -> str | None:
    """Return the name of the NamedTuple class passed via `class X(ConnectionInfo, key=Y)`.

    v0.5: replaces `key_fields_value`-based arity inference. Walks the class
    bases and keyword args. Returns None if `key=` is absent (default `_DefaultKey`).
    """
    for kw in cls.keywords:
        if kw.arg == "key" and isinstance(kw.value, ast.Name):
            return kw.value.id
    return None


def namedtuple_field_count(tree: ast.AST, name: str) -> int | None:
    """For a top-level `class <name>(NamedTuple): ...` in `tree`, return field count.

    Recognises plain `field: type` annotations inside the class body. Returns
    None if no matching class found, or the body is not statically resolvable.
    """
    if not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != name:
            continue
        # Check NamedTuple base.
        is_nt = False
        for base in node.bases:
            base_name = base.attr if isinstance(base, ast.Attribute) else (base.id if isinstance(base, ast.Name) else None)
            if base_name == "NamedTuple":
                is_nt = True
                break
        if not is_nt:
            return None
        count = 0
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                count += 1
        return count
    return None


def local_pydantic_classes(tree: ast.AST) -> set[str]:
    """Top-level class names whose base is `BaseModel` or `ConnectionInfo`."""
    found: set[str] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            base_name = base.attr if isinstance(base, ast.Attribute) else (base.id if isinstance(base, ast.Name) else None)
            if base_name in {"BaseModel", "ConnectionInfo"}:
                found.add(node.name)
                break
    return found


# --------------------------------------------------------------------------- #
# A2K012 v0.7 — resolve `from <pkg> import NAME` through `__init__.py`
# re-export chains, so `Final[str]` constants survive a single-level wrap.
# --------------------------------------------------------------------------- #


def _module_to_path(module_name: str, project_root: Path) -> Path | None:
    """Map `pkg.sub` to either `pkg/sub.py` or `pkg/sub/__init__.py`. None if missing."""
    parts = module_name.split(".")
    pkg_init = project_root.joinpath(*parts) / "__init__.py"
    if pkg_init.is_file():
        return pkg_init
    mod_py = project_root.joinpath(*parts).with_suffix(".py")
    if mod_py.is_file():
        return mod_py
    return None


def _has_final_str_assign(tree: ast.AST, name: str) -> bool:
    """True if `name: Final[str] = ...` exists at module scope in `tree`."""
    if not isinstance(tree, ast.Module):  # pragma: no cover — driver always passes Module
        return False
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        if stmt.target.id != name:  # pragma: no cover — early-skip during walk
            continue
        anno = stmt.annotation
        if not isinstance(anno, ast.Subscript):  # pragma: no cover — defensive
            continue
        base = anno.value
        base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
        if base_name != "Final":  # pragma: no cover — defensive
            continue
        slice_node = anno.slice
        if isinstance(slice_node, ast.Name) and slice_node.id == "str":
            return True
    return False


def _find_reexport(tree: ast.AST, name: str) -> str | None:
    """Find `from <module> import <name>` (or `as <name>`) at top-level. Returns module."""
    if not isinstance(tree, ast.Module):  # pragma: no cover — driver always passes Module
        return None
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom) or stmt.module is None:
            continue
        for alias in stmt.names:
            local = alias.asname or alias.name
            if local == name:
                return stmt.module
    return None


_REEXPORT_CACHE: dict[tuple[str, str, str], bool] = {}


def resolve_through_reexports(
    module_name: str,
    attr_name: str,
    project_root: Path,
    *,
    max_depth: int = 3,
) -> bool:
    """Walk `__init__.py` re-export chains; return True if `attr_name` resolves to `Final[str]`.

    Caps at `max_depth` to avoid pathological infinite loops. Caches per-scan
    keyed by `(project_root, module_name, attr_name)`.
    """
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


def reset_reexport_cache() -> None:
    """Test seam — drop cached reexport resolutions."""
    _REEXPORT_CACHE.clear()
