"""Core-purity rules.

- A2K-CORE-CLEAN — ``src/a2kit/*.py`` (excluding ``packages/``) MAY NOT reference
  feature-specific identifiers (``connection``, ``enricher``, ``list_view``,
  ``report_type``, ``report_schema``, ``router_slug``) by name.
- A2K-EXTRA-NAMESPACE — keys written to ``A2KitMeta.extra`` must start with
  ``a2kit.`` or a registered ``<package>.`` prefix.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K_CORE_CLEAN,
    A2K_EXTRA_NAMESPACE,
    LintMessage,
    _msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


_FORBIDDEN_CORE_TOKENS = frozenset(
    {
        "connection",
        "connection_key",
        "connections",
        "enricher",
        "list_view",
        "report_type",
        "report_schema",
        "router_slug",
    }
)

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*\.")


def _is_core_path(filename: str) -> bool:
    """True for files in ``src/a2kit/*.py`` outside ``packages/``."""
    norm = filename.replace("\\", "/")
    if "src/a2kit/" not in norm:
        return False
    after = norm.split("src/a2kit/", 1)[1]
    if "/" not in after:
        return True
    head = after.split("/", 1)[0]
    return head != "packages"


def _node_identifier(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.keyword):
        return node.arg
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return None


def rule_core_clean(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    if not _is_core_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        ident = _node_identifier(node)
        if ident is None or ident not in _FORBIDDEN_CORE_TOKENS:
            continue
        line = getattr(node, "lineno", 1)
        if suppressed(noqa, A2K_CORE_CLEAN, line):
            continue
        yield _msg(
            A2K_CORE_CLEAN,
            filename,
            node,
            f"core source MUST NOT reference feature identifier {ident!r}; move to a2kit.packages.* and attach via A2KitMeta.extra",
        )


def _extra_subscript_writes(tree: ast.AST) -> Iterable[tuple[ast.AST, str]]:
    """Yield (node, key) for ``<x>.extra[<str-literal>] = ...`` assignments."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            value = tgt.value
            if not (isinstance(value, ast.Attribute) and value.attr == "extra"):
                continue
            slc = tgt.slice
            if isinstance(slc, ast.Constant) and isinstance(slc.value, str):
                yield tgt, slc.value


def _extra_dict_in_meta(tree: ast.AST) -> Iterable[tuple[ast.AST, str]]:
    """Yield (node, key) for ``A2KitMeta(extra={<str-literal>: ...})`` constructor calls."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
        if name != "A2KitMeta":
            continue
        for kw in node.keywords:
            if kw.arg != "extra" or not isinstance(kw.value, ast.Dict):
                continue
            for k in kw.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    yield k, k.value


def rule_extra_namespace(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    sources = list(_extra_subscript_writes(tree)) + list(_extra_dict_in_meta(tree))
    for node, key in sources:
        if key.startswith("a2kit.") or _PREFIX_RE.match(key):
            continue
        line = getattr(node, "lineno", 1)
        if suppressed(noqa, A2K_EXTRA_NAMESPACE, line):
            continue
        yield _msg(
            A2K_EXTRA_NAMESPACE,
            filename,
            node,
            f"A2KitMeta.extra key {key!r} must start with 'a2kit.' or a '<package>.' prefix",
        )


__all__ = ["rule_core_clean", "rule_extra_namespace"]
