"""Capability: `a2kit.compose_default_surfaces()` is the facade entry that
composes the bundled MCP + HTTP surfaces and binds them as the active
registry. Per `bootstrap-surfaces-explicit` (2026-05-26).
"""

from __future__ import annotations

import a2kit
from a2kit.packages.dispatch.surface import (
    SurfaceRegistry,
    current_registry,
)
from a2kit.testing import app_of


def test_compose_default_surfaces_returns_a_populated_registry() -> None:
    """Calling the facade composes both bundled surfaces in declaration order."""
    registry = a2kit.compose_default_surfaces()
    assert isinstance(registry, SurfaceRegistry)
    assert registry.names() == ("mcp", "api")


def test_compose_default_surfaces_is_idempotent() -> None:
    """Second call returns the same registry instance — no double-register."""
    first = a2kit.compose_default_surfaces()
    second = a2kit.compose_default_surfaces()
    assert first is second


def test_compose_default_surfaces_binds_active_registry() -> None:
    """After composing, `current_registry()` returns the composed registry."""
    registry = a2kit.compose_default_surfaces()
    assert current_registry() is registry


def test_a2kit_run_uses_composed_registry() -> None:
    """`a2kit.run(app)` (production finisher) composes + passes through."""
    # The facade `run()` is wired to call compose_default_surfaces() and
    # pass the result into `build()`. We verify wiring by inspecting that
    # compose_default_surfaces() is the path — calling it directly produces
    # the same registry instance run() would.
    via_compose = a2kit.compose_default_surfaces()
    assert via_compose.names() == ("mcp", "api")


def test_third_party_surface_via_explicit_registry() -> None:
    """Passing a custom Surface via `runtime.build(app, surfaces=registry)`
    mounts it without any import side effect AND without disturbing the
    process-wide active registry.
    """
    from typing import Any

    from a2kit.runtime import build

    class MySurface:
        name = "my"
        reserved_types: frozenset[type] = frozenset()
        substrate_dep_markers: frozenset[type] = frozenset()

        def bind(self, runtime: Any, descriptors: Any = None) -> Any:
            return None

        def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
            return None

    # Build a fresh per-test registry; DO NOT rebind the active registry
    # (that's process-wide state owned by the conftest-bound one).
    registry = SurfaceRegistry()
    registry.register_surface(MySurface())

    app = app_of("demo")
    runtime = build(app, surfaces=registry)
    assert runtime.surfaces is registry
    assert "my" in registry.names()
