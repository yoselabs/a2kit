"""Static (AST-only) lint rules: A2K001..A2K006.

Each rule yields `LintMessage`s. No imports are executed during analysis.
Cross-tool rules (A2K006) walk multiple files in `run_static_rules`.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import (
    connection_info_subclasses,
    decorator_kwargs,
    function_has_param,
    is_a2kit_tool_decorator,
    is_tool_function,
    key_fields_value,
    local_pydantic_classes,
)
from a2kit.lint._common import LintMessage, parse_noqa, suppressed

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

A2K001 = "A2K001"
A2K002 = "A2K002"
A2K003 = "A2K003"
A2K004 = "A2K004"
A2K005 = "A2K005"
A2K006 = "A2K006"
A2K008 = "A2K008"
A2K009 = "A2K009"

ALL_RULES = (A2K001, A2K002, A2K003, A2K004, A2K005, A2K006, A2K008, A2K009)

_BUILTIN_CAPS = {"read", "write", "destructive", "expensive", "pii", "external"}


_FIXTURE_PATH_TOKENS = ("tests/", "tests\\", "examples/", "examples\\")


def _is_fixture_path(filename: str) -> bool:
    """A2K003/A2K004 don't apply to test or example files (they create disposable
    Pydantic models / connection-param tools to exercise the library)."""
    return any(token in filename for token in _FIXTURE_PATH_TOKENS)


def _msg(rule: str, filename: str, node: ast.AST, text: str) -> LintMessage:
    return LintMessage(
        rule=rule,
        filename=filename,
        line=getattr(node, "lineno", 1),
        col=getattr(node, "col_offset", 0),
        message=text,
    )


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
                yield _msg(A2K001, filename, node, f"function {node.name!r} missing connection_param {cp.value!r}")


def rule_a2k002(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K002 — Tools must not declare `-> str` return."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_str = (isinstance(ret, ast.Name) and ret.id == "str") or (isinstance(ret, ast.Constant) and ret.value == "str")
        if is_str and not suppressed(noqa, A2K002, node.lineno):
            yield _msg(A2K002, filename, node, f"tool {node.name!r} declares `-> str`; FastMCP double-serialises")


def rule_a2k003(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K003 — Tools should not return locally-defined Pydantic models."""
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    locals_ = local_pydantic_classes(tree)
    if not locals_:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret_name = node.returns.id if isinstance(node.returns, ast.Name) else None
        if ret_name in locals_ and not suppressed(noqa, A2K003, node.lineno):
            yield _msg(A2K003, filename, node, f"tool {node.name!r} returns module-local Pydantic model {ret_name!r}")


def rule_a2k004(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K004 — Tools with `connection` param should reference the canonical helper."""
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    if "connection_param_doc" in source:
        # The module references the helper; that satisfies the rule.
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or not function_has_param(node, "connection"):
            continue
        if suppressed(noqa, A2K004, node.lineno):
            continue
        yield _msg(
            A2K004,
            filename,
            node,
            f"tool {node.name!r} has `connection` param but no a2kit.docs.connection_param_doc reference",
        )


def _check_key_fields_value(cls: ast.ClassDef, kf: ast.expr, filename: str, noqa: dict) -> Iterable[LintMessage]:
    if suppressed(noqa, A2K005, cls.lineno):
        return
    if not isinstance(kf, ast.Tuple):
        yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS must be a tuple of strings")
        return
    for elt in kf.elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS contains non-string element")
            continue
        v = elt.value
        if not v.isidentifier():
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS element {v!r} is not a valid identifier")
        elif v != v.lower():
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS element {v!r} should be lowercase")


def rule_a2k005(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K005 — `KEY_FIELDS` must be a tuple of lowercase string identifiers."""
    noqa = parse_noqa(source)
    for cls in connection_info_subclasses(tree):
        kf = key_fields_value(cls)
        if kf is None:
            continue
        yield from _check_key_fields_value(cls, kf, filename, noqa)


def _collect_param_descriptions(tree: ast.AST) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        doc = ast.get_docstring(node) or ""
        for raw in doc.splitlines():
            line = raw.strip()
            if ":" not in line:
                continue
            name, _, text = line.partition(":")
            name = name.strip()
            text = text.strip()
            if not name.isidentifier() or len(text) < 20:
                continue
            out.setdefault(name, []).append(text)
    return out


def _rule_a2k006_cross(per_file: dict[str, dict[str, list[str]]]) -> Iterable[LintMessage]:
    flat: dict[tuple[str, str], list[str]] = {}
    for filename, mapping in per_file.items():
        for name, texts in mapping.items():
            for t in texts:
                flat.setdefault((name, t), []).append(filename)
    for (name, _t), files in flat.items():
        if len(files) >= 3:
            yield LintMessage(
                rule=A2K006,
                filename=files[0],
                line=1,
                col=0,
                message=(f"param {name!r} has the same description in {len(files)} tools; consider a2kit.docs.register_param_doc"),
            )


def rule_a2k009(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K009 — Raw built-in capability string.

    `capabilities={'write'}` literal where `Cap.WRITE` is type-safer. Warning.
    Skipped under tests/ and examples/ (test fixtures often use raw strings on
    purpose to exercise the rule itself or for brevity).
    """
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            for raw in _iter_string_literals(kw.value):
                if raw.value in _BUILTIN_CAPS and not suppressed(noqa, A2K009, raw.lineno):
                    suggestion = f"Cap.{raw.value.upper()}"
                    yield _msg(
                        A2K009,
                        filename,
                        raw,
                        f"raw built-in capability string {raw.value!r}; prefer {suggestion}",
                    )


def _iter_string_literals(node: ast.expr) -> Iterable[ast.Constant]:
    """Yield string-constant elements inside a set/list/tuple literal."""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                yield elt


def _collect_router_names(tree: ast.AST) -> set[str]:
    """Best-effort: pull names from `Router(name='...')` / `Feature` subclass `name = '...'`."""
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


def _collect_tool_names(tree: ast.AST) -> set[str]:
    """Tool names = function names of `@a2kit.tool(...)` decorated functions, plus explicit tool_name=."""
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
            # Include the function name as a candidate tool name.
            out.add(node.name)
            break
    return out


def _rule_a2k008_cross(per_file: dict[str, tuple[set[str], set[str]]]) -> Iterable[LintMessage]:
    """A2K008 — name collision: a router name, capability name, and tool name overlap."""
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
    collisions = (all_routers & all_tools) | (all_routers & _BUILTIN_CAPS) | (all_tools & _BUILTIN_CAPS)
    for name in sorted(collisions):
        filename = first_seen.get(name, "<unknown>")
        yield LintMessage(
            rule=A2K008,
            filename=filename,
            line=1,
            col=0,
            message=f"name {name!r} collides across router/tool/capability namespaces",
        )


_RULES_PER_FILE = (
    (A2K001, rule_a2k001),
    (A2K002, rule_a2k002),
    (A2K003, rule_a2k003),
    (A2K004, rule_a2k004),
    (A2K005, rule_a2k005),
    (A2K009, rule_a2k009),
)


def run_static_rules(paths: Iterable[Path], *, disabled: Iterable[str] = ()) -> list[LintMessage]:
    """Run all static rules on `paths`. Returns concatenated findings."""
    disabled_set = set(disabled)
    results: list[LintMessage] = []
    per_file_a2k006: dict[str, dict[str, list[str]]] = {}
    per_file_a2k008: dict[str, tuple[set[str], set[str]]] = {}
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for code, rule in _RULES_PER_FILE:
            if code in disabled_set:
                continue
            results.extend(rule(tree, str(path), source))
        if A2K006 not in disabled_set:
            per_file_a2k006[str(path)] = _collect_param_descriptions(tree)
        if A2K008 not in disabled_set and not _is_fixture_path(str(path)):
            per_file_a2k008[str(path)] = (_collect_router_names(tree), _collect_tool_names(tree))
    if A2K006 not in disabled_set:
        results.extend(_rule_a2k006_cross(per_file_a2k006))
    if A2K008 not in disabled_set:
        results.extend(_rule_a2k008_cross(per_file_a2k008))
    return results
