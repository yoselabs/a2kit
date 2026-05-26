"""Unit tests for the A2K-SURFACE-REGISTRY lint rule."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.surface_registry import rule_surface_registry


def _findings(source: str) -> list:
    tree = ast.parse(source)
    return list(rule_surface_registry(tree, "test.py", source))


def test_surface_with_manifest_passes() -> None:
    source = """
from a2kit.packages.dispatch.surface import DecoratorSurface

class MySurface(DecoratorSurface):
    name = "my"

MANIFEST = object()  # placeholder; rule only checks for the name
"""
    assert _findings(source) == []


def test_surface_without_manifest_fails() -> None:
    source = """
from a2kit.packages.dispatch.surface import DecoratorSurface

class MySurface(DecoratorSurface):
    name = "my"
"""
    msgs = _findings(source)
    assert len(msgs) == 1
    assert msgs[0].rule == "A2K-SURFACE-REGISTRY"
    assert "MySurface" in msgs[0].message
    assert "MANIFEST" in msgs[0].message


def test_module_without_surface_subclass_is_ignored() -> None:
    source = """
class NotASurface:
    pass
"""
    assert _findings(source) == []


def test_generic_surface_base_is_recognised() -> None:
    """`DecoratorSurface[Registration]` (subscripted) is treated as a base."""
    source = """
from a2kit.packages.dispatch.surface import DecoratorSurface

class MySurface(DecoratorSurface[object]):
    name = "my"
"""
    msgs = _findings(source)
    assert len(msgs) == 1
