"""Cross-file aggregating rules.

- A2K006 — repeated param descriptions across multiple tools.
- A2K008 — router/tool/capability namespace collisions.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.rules.detect import is_tool_function
from a2kit.packages.lint.static import A2K006, A2K008, BUILTIN_CAPS, LintMessage

if TYPE_CHECKING:
    from collections.abc import Iterable


def collect_param_descriptions(tree: ast.AST) -> dict[str, list[str]]:
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


def rule_a2k006_cross(per_file: dict[str, dict[str, list[str]]]) -> Iterable[LintMessage]:
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


def collect_router_names(tree: ast.AST) -> set[str]:
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


__all__ = [
    "collect_param_descriptions",
    "collect_router_names",
    "collect_tool_names",
    "rule_a2k006_cross",
    "rule_a2k008_cross",
]
