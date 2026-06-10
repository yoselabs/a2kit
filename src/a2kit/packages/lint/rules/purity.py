"""Core-purity rules.

- A2K-EXTRA-NAMESPACE — attributes assigned through ``A2KitMeta.extras`` must
  be one of the typed-extras field names declared on
  :class:`a2kit.metadata.A2KitMetaExtras`.

A2K-CORE-CLEAN (the string-token blocklist on core source) was retired in
v0.34. The typed-extras model itself enforces "feature-specific attributes
must be declared on A2KitMetaExtras"; A2K-EXTRA-NAMESPACE catches the same
class of bug structurally rather than by token-matching.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K_EXTRA_NAMESPACE,
    LintMessage,
    _msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


#: Permitted attribute names on ``A2KitMeta.extras`` / ``A2KitMetaExtras(...)``.
#: Mirror of the fields declared on ``a2kit.metadata.A2KitMetaExtras``. When
#: a field is added to the model, add it here too — the test in
#: ``tests/test_metadata_extras.py`` (or similar) catches drift.
_TYPED_EXTRAS_FIELDS = frozenset(
    {
        "report_type",
        "report_schema",
        "router_slug",
        "list_view",
        "timeout_seconds",
        "expose",
        "authorize",
    }
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


__all__ = ["rule_extra_namespace"]
