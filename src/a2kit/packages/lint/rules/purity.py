"""Core-purity rules.

- A2K-CORE-CLEAN — ``src/a2kit/*.py`` (excluding ``packages/``) MAY NOT reference
  feature-specific identifiers (``connection``, ``enricher``, ``list_view``,
  ``report_type``, ``report_schema``, ``router_slug``) by name.
- A2K-EXTRA-NAMESPACE — attributes assigned through ``A2KitMeta.extras`` must
  be one of the typed-extras field names declared on
  :class:`a2kit.metadata.A2KitMetaExtras`.

The post-R4 surface ``meta.extras.<attr> = ...`` no longer carries arbitrary
string keys; the rule shifts from "namespace your key string" to "this
attribute is declared on the typed extras model." Larger purity-rule rework
lives in the sibling ``loud-degrade-everywhere`` proposal.
"""

from __future__ import annotations

import ast
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

#: Permitted attribute names on ``A2KitMeta.extras`` / ``A2KitMetaExtras(...)``.
_TYPED_EXTRAS_FIELDS = frozenset(
    {
        "report_type",
        "report_schema",
        "router_slug",
        "surfaces",
        "list_view",
    }
)


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
            f"core source MUST NOT reference feature identifier {ident!r}; move to a2kit.packages.* and attach via A2KitMeta.extras",
        )


def _extras_attribute_writes(tree: ast.AST) -> Iterable[tuple[ast.AST, str]]:
    """Yield (node, attr) for ``<x>.extras.<attr> = ...`` assignments.

    Matches the post-R4 typed-extras write shape: an ``ast.Assign`` whose
    target is an ``ast.Attribute`` chain ending in
    ``Attribute(.value = Attribute(attr="extras"), attr=<name>)``.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Attribute):
                continue
            parent = tgt.value
            if isinstance(parent, ast.Attribute) and parent.attr == "extras":
                yield tgt, tgt.attr


def _extras_kwarg_in_meta(tree: ast.AST) -> Iterable[tuple[ast.AST, str]]:
    """Yield (node, kwarg) for ``A2KitMetaExtras(<kwarg>=...)`` constructor calls."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)
        if name != "A2KitMetaExtras":
            continue
        for kw in node.keywords:
            if kw.arg is None:
                continue
            yield kw, kw.arg


def rule_extra_namespace(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    sources = list(_extras_attribute_writes(tree)) + list(_extras_kwarg_in_meta(tree))
    for node, attr in sources:
        if attr in _TYPED_EXTRAS_FIELDS:
            continue
        line = getattr(node, "lineno", 1)
        if suppressed(noqa, A2K_EXTRA_NAMESPACE, line):
            continue
        yield _msg(
            A2K_EXTRA_NAMESPACE,
            filename,
            node,
            (
                f"A2KitMeta.extras attribute {attr!r} is not declared on "
                "A2KitMetaExtras; add it to the typed model or stage via a "
                "registered package extension"
            ),
        )


__all__ = ["rule_core_clean", "rule_extra_namespace"]
