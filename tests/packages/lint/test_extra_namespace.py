"""A2K-EXTRA-NAMESPACE: A2KitMeta.extra keys must be namespaced."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.purity import rule_extra_namespace


def _run(source: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_extra_namespace(tree, "x.py", source)]


def test_accepts_a2kit_namespace_subscript() -> None:
    msgs = _run('m.extra["a2kit.enricher"] = fn\n')
    assert msgs == []


def test_rejects_bare_key_subscript() -> None:
    msgs = _run('m.extra["enricher"] = fn\n')
    assert any("enricher" in m for m in msgs)


def test_accepts_third_party_prefix() -> None:
    msgs = _run('m.extra["acme_plugin.policy"] = "strict"\n')
    assert msgs == []


def test_rejects_uppercase_prefix() -> None:
    msgs = _run('m.extra["Foo.bar"] = 1\n')
    assert msgs


def test_accepts_constructor_namespaced() -> None:
    msgs = _run('A2KitMeta(extra={"a2kit.report_type": int})\n')
    assert msgs == []


def test_rejects_constructor_bare() -> None:
    msgs = _run('A2KitMeta(extra={"enricher": fn})\n')
    assert msgs


def test_noqa_suppresses() -> None:
    msgs = _run('m.extra["enricher"] = fn  # noqa: A2K-EXTRA-NAMESPACE\n')
    assert msgs == []
