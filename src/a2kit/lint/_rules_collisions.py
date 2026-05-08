"""Cross-file rules: name-collision detection + select-atom validation.

A2K008 — router/tool/capability namespace collision (cross-file).
A2K010 — unknown atom in `--select` strings (project-wide; reads pyproject,
         shell scripts, and source).
"""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.lint._common import (
    A2K008,
    A2K010,
    BUILTIN_CAPS,
    LintMessage,
    is_fixture_path,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def collect_router_names(tree: ast.AST) -> set[str]:
    """Pull names from `Router(name='...')` calls and class-level `name = '...'` assignments."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.add(kw.value.value)
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if (
                            isinstance(tgt, ast.Name)
                            and tgt.id == "name"
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)
                        ):
                            out.add(stmt.value.value)
    return out


def collect_tool_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            for kw in dec.keywords:
                if kw.arg == "tool_name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.add(kw.value.value)
                    break
            out.add(node.name)
            break
    return out


def rule_a2k008_cross(per_file: dict[str, tuple[set[str], set[str]]]) -> Iterable[LintMessage]:
    all_routers: set[str] = set()
    all_tools: set[str] = set()
    first_seen: dict[str, str] = {}
    for filename, (routers, tools) in per_file.items():
        for r in routers:
            first_seen.setdefault(r, filename)
        for t in tools:
            first_seen.setdefault(t, filename)
        all_routers.update(routers)
        all_tools.update(tools)
    collisions = (all_routers & all_tools) | (all_routers & BUILTIN_CAPS) | (all_tools & BUILTIN_CAPS)
    for name in sorted(collisions):
        filename = first_seen.get(name, "<unknown>")
        yield LintMessage(
            rule=A2K008,
            filename=filename,
            line=1,
            col=0,
            message=f"name {name!r} collides across router/tool/capability namespaces",
        )


_SELECT_ATTRS = ("select", "default_select")


def _select_strings_from_kwargs(call: ast.Call) -> Iterable[tuple[ast.AST, str]]:
    """`select=...` / `default_select=...` literal kwargs."""
    for kw in call.keywords:
        if kw.arg in _SELECT_ATTRS and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            yield (kw.value, kw.value.value)


def _select_strings_from_argv_lists(call: ast.Call) -> Iterable[tuple[ast.AST, str]]:
    """`["--select", "<expr>", ...]` argv literals passed positionally."""
    for arg in call.args:
        if not isinstance(arg, (ast.List, ast.Tuple)):
            continue
        elts = arg.elts
        for i, elt in enumerate(elts[:-1]):
            nxt = elts[i + 1]
            if isinstance(elt, ast.Constant) and elt.value == "--select" and isinstance(nxt, ast.Constant) and isinstance(nxt.value, str):
                yield (nxt, nxt.value)


def _select_strings_from_parse_select(call: ast.Call) -> Iterable[tuple[ast.AST, str]]:
    """`parse_select("<expr>")` direct calls."""
    callee = call.func
    cname = callee.id if isinstance(callee, ast.Name) else (callee.attr if isinstance(callee, ast.Attribute) else None)
    if cname == "parse_select" and call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        yield (call.args[0], call.args[0].value)


def collect_select_strings_from_source(tree: ast.AST) -> list[tuple[ast.AST, str]]:
    """Pull `--select "<expr>"` and `default_select=...` literals from a file."""
    out: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        out.extend(_select_strings_from_kwargs(node))
        out.extend(_select_strings_from_argv_lists(node))
        out.extend(_select_strings_from_parse_select(node))
    return out


def _select_atoms(expr_str: str) -> list[tuple[str | None, str]] | None:
    """Tokenise a select expression into (namespace, name) atoms. None on parse error."""
    try:
        from a2kit._select import parse_select  # noqa: PLC0415

        ast_node = parse_select(expr_str)
    except (ValueError, Exception):  # noqa: BLE001
        return None
    out: list[tuple[str | None, str]] = []

    def walk(node: object) -> None:
        op = getattr(node, "op", None)
        if op == "atom":
            atom = getattr(node, "atom", None)
            if atom is None:  # pragma: no cover — well-formed atoms always carry .atom
                return
            out.append((atom.namespace, atom.name))
            return
        for c in getattr(node, "children", []):
            walk(c)

    walk(ast_node)
    return out


def scan_pyproject_select(start: Path) -> str | None:
    """Read `[tool.a2kit.runner] default_select` from the nearest pyproject.toml."""
    import tomllib  # noqa: PLC0415

    cur = start.resolve() if start.exists() else Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):  # pragma: no cover — defensive
                return None
            return data.get("tool", {}).get("a2kit", {}).get("runner", {}).get("default_select")
    return None


def scan_shell_select_strings(paths: list[Path]) -> list[tuple[Path, int, str]]:
    """Grep `.sh` files and Makefiles for `--select "<expr>"` literals."""
    out: list[tuple[Path, int, str]] = []
    for path in paths:
        if path.suffix != ".sh" and path.name != "Makefile":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover — defensive
            continue
        for lineno, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            idx = stripped.find("--select")
            if idx == -1:
                continue
            tail = stripped[idx + len("--select") :].lstrip()
            if not tail:  # pragma: no cover — `--select` always followed by something usable
                continue
            quote = tail[0]
            if quote not in {'"', "'"}:  # pragma: no cover — supported forms only
                continue
            end = tail.find(quote, 1)
            if end == -1:  # pragma: no cover — malformed quoting
                continue
            out.append((path, lineno, tail[1:end]))
    return out


def resolve_known_atoms_from_files(per_file: dict[str, tuple[set[str], set[str]]]) -> set[str]:
    """Union of router + tool names across the linted file set."""
    routers: set[str] = set()
    tools: set[str] = set()
    for r, t in per_file.values():
        routers |= r
        tools |= t
    return routers | tools | BUILTIN_CAPS | {"default"}


def rule_a2k010(
    pyproject_select: str | None,
    source_findings: list[tuple[Path, ast.AST, str]],
    shell_findings: list[tuple[Path, int, str]],
    known_atoms: set[str],
    *,
    pyproject_path: Path | None = None,
) -> Iterable[LintMessage]:
    """Validate `--select` atoms against `known_atoms`. Unknown → A2K010."""
    pools = sorted(known_atoms)

    def check(atoms: list[tuple[str | None, str]] | None, filename: str, line: int, col: int) -> Iterable[LintMessage]:
        if atoms is None:
            return
        for _ns, name in atoms:
            if name in known_atoms:
                continue
            hits = difflib.get_close_matches(name, pools, n=2)
            suggestion = f" Did you mean: {', '.join(hits)}?" if hits else ""
            yield LintMessage(
                rule=A2K010,
                filename=filename,
                line=line,
                col=col,
                message=f"unknown --select atom {name!r}.{suggestion}",
            )

    if pyproject_select is not None:
        atoms = _select_atoms(pyproject_select)
        target = str(pyproject_path) if pyproject_path else "pyproject.toml"
        yield from check(atoms, target, 1, 0)

    for path, node, value in source_findings:
        atoms = _select_atoms(value)
        yield from check(atoms, str(path), getattr(node, "lineno", 1), getattr(node, "col_offset", 0))

    for path, lineno, value in shell_findings:
        atoms = _select_atoms(value)
        yield from check(atoms, str(path), lineno, 0)


# Re-export `is_fixture_path` so the driver can access it via this module.
__all__ = [
    "collect_router_names",
    "collect_select_strings_from_source",
    "collect_tool_names",
    "is_fixture_path",
    "resolve_known_atoms_from_files",
    "rule_a2k008_cross",
    "rule_a2k010",
    "scan_pyproject_select",
    "scan_shell_select_strings",
]
