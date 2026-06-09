"""Tests for `a2kit.packages.lint.rules.purity` (A2K-EXTRA-NAMESPACE).

A2K-CORE-CLEAN (the string-token blocklist on core source) was retired in
v0.34; the typed-extras model + A2K-EXTRA-NAMESPACE enforces the same
boundary structurally.
"""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.purity import rule_extra_namespace


# --- A2K-EXTRA-NAMESPACE --------------------------------------------------- #


def _run_extra(source: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_extra_namespace(tree, "x.py", source)]


def test_accepts_typed_extras_field_write() -> None:
    msgs = _run_extra("m.extras.report_type = int\n")
    assert msgs == []


def test_rejects_unknown_extras_attr_write() -> None:
    msgs = _run_extra("m.extras.enricher = fn\n")
    assert any("enricher" in m for m in msgs)


def test_accepts_typed_extras_constructor() -> None:
    msgs = _run_extra("A2KitMetaExtras(report_type=int)\n")
    assert msgs == []


def test_rejects_unknown_extras_constructor_kwarg() -> None:
    msgs = _run_extra("A2KitMetaExtras(enricher=fn)\n")
    assert msgs


def test_extra_namespace_noqa_suppresses() -> None:
    msgs = _run_extra("m.extras.enricher = fn  # noqa: AK208\n")
    assert msgs == []
