"""Tests for `a2kit.packages.lint.rules.purity` (A2K-CORE-CLEAN + A2K-EXTRA-NAMESPACE).

Merged from `tests/packages/lint/test_core_purity.py` and
`tests/packages/lint/test_extra_namespace.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.purity import rule_core_clean, rule_extra_namespace


# --- A2K-CORE-CLEAN -------------------------------------------------------- #


def _run_core(source: str, filename: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_core_clean(tree, filename, source)]


def test_flags_connection_attr_in_core() -> None:
    source = "class X:\n    def __init__(self):\n        self.connection_key = ()\n"
    msgs = _run_core(source, "src/a2kit/exceptions.py")
    assert any("connection_key" in m for m in msgs)


def test_flags_enricher_kwarg_in_core() -> None:
    source = "def f(*, enricher=None): pass\n"
    msgs = _run_core(source, "src/a2kit/tool.py")
    assert any("enricher" in m for m in msgs)


def test_flags_router_slug_field() -> None:
    source = "class M:\n    router_slug: str | None = None\n"
    msgs = _run_core(source, "src/a2kit/metadata.py")
    assert msgs


def test_docstring_mentioning_connection_is_allowed() -> None:
    source = '"""Tool that takes a connection name."""\n'
    msgs = _run_core(source, "src/a2kit/app.py")
    assert msgs == []


def test_packages_subtree_is_exempt() -> None:
    source = "class X:\n    def __init__(self):\n        self.connection_key = ()\n"
    msgs = _run_core(source, "src/a2kit/packages/connections/exceptions.py")
    assert msgs == []


def test_non_core_file_exempt() -> None:
    source = "enricher = None\n"
    msgs = _run_core(source, "tests/test_app.py")
    assert msgs == []


def test_noqa_suppresses() -> None:
    source = "enricher = None  # noqa: A2K-CORE-CLEAN\n"
    msgs = _run_core(source, "src/a2kit/tool.py")
    assert msgs == []


# --- A2K-EXTRA-NAMESPACE --------------------------------------------------- #


def _run_extra(source: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_extra_namespace(tree, "x.py", source)]


def test_accepts_a2kit_namespace_subscript() -> None:
    msgs = _run_extra('m.extra["a2kit.enricher"] = fn\n')
    assert msgs == []


def test_rejects_bare_key_subscript() -> None:
    msgs = _run_extra('m.extra["enricher"] = fn\n')
    assert any("enricher" in m for m in msgs)


def test_accepts_third_party_prefix() -> None:
    msgs = _run_extra('m.extra["acme_plugin.policy"] = "strict"\n')
    assert msgs == []


def test_rejects_uppercase_prefix() -> None:
    msgs = _run_extra('m.extra["Foo.bar"] = 1\n')
    assert msgs


def test_accepts_constructor_namespaced() -> None:
    msgs = _run_extra('A2KitMeta(extra={"a2kit.report_type": int})\n')
    assert msgs == []


def test_rejects_constructor_bare() -> None:
    msgs = _run_extra('A2KitMeta(extra={"enricher": fn})\n')
    assert msgs


def test_extra_namespace_noqa_suppresses() -> None:
    msgs = _run_extra('m.extra["enricher"] = fn  # noqa: A2K-EXTRA-NAMESPACE\n')
    assert msgs == []
