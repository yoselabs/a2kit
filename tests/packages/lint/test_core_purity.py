"""A2K-CORE-CLEAN: forbid feature identifiers in src/a2kit/*.py (excluding packages/)."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.purity import rule_core_clean


def _run(source: str, filename: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_core_clean(tree, filename, source)]


def test_flags_connection_attr_in_core() -> None:
    source = "class X:\n    def __init__(self):\n        self.connection_key = ()\n"
    msgs = _run(source, "src/a2kit/exceptions.py")
    assert any("connection_key" in m for m in msgs)


def test_flags_enricher_kwarg_in_core() -> None:
    source = "def f(*, enricher=None): pass\n"
    msgs = _run(source, "src/a2kit/tool.py")
    assert any("enricher" in m for m in msgs)


def test_flags_router_slug_field() -> None:
    source = "class M:\n    router_slug: str | None = None\n"
    msgs = _run(source, "src/a2kit/metadata.py")
    assert msgs


def test_docstring_mentioning_connection_is_allowed() -> None:
    source = '"""Tool that takes a connection name."""\n'
    msgs = _run(source, "src/a2kit/app.py")
    assert msgs == []


def test_packages_subtree_is_exempt() -> None:
    source = "class X:\n    def __init__(self):\n        self.connection_key = ()\n"
    msgs = _run(source, "src/a2kit/packages/connections/exceptions.py")
    assert msgs == []


def test_non_core_file_exempt() -> None:
    source = "enricher = None\n"
    msgs = _run(source, "tests/test_app.py")
    assert msgs == []


def test_noqa_suppresses() -> None:
    source = "enricher = None  # noqa: A2K-CORE-CLEAN\n"
    msgs = _run(source, "src/a2kit/tool.py")
    assert msgs == []
