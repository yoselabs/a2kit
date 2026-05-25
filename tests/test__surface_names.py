"""Kernel-layer surface name registry (``a2kit._surface_names``).

Covers the ``surface-protocol`` ADDED requirement that
``SurfaceRegistry.register_surface()`` side-effects ``s.name`` into the
kernel name registry, and that the API itself is idempotent and ordered.
"""

from __future__ import annotations

from a2kit._surface_names import (
    _REGISTERED_SURFACE_NAMES,
    register_surface_name,
    registered_surface_names,
)


def test_bundled_surfaces_are_registered() -> None:
    """conftest eagerly imports ``a2kit.packages.{mcp,http}``."""
    names = registered_surface_names()
    assert "mcp" in names
    assert "api" in names


def test_registered_surface_names_returns_tuple() -> None:
    names = registered_surface_names()
    assert isinstance(names, tuple)
    assert all(isinstance(n, str) for n in names)


def test_register_surface_name_is_idempotent() -> None:
    before = registered_surface_names()
    register_surface_name("mcp")
    after = registered_surface_names()
    assert before == after


def test_register_then_query_via_registry() -> None:
    """Registering through the dispatch ``SurfaceRegistry`` populates the
    kernel name list as a side-effect.
    """
    from typing import Any

    from a2kit.packages.dispatch import SURFACE_REGISTRY

    class _StubSurface:
        name = "stub_for_name_registry"
        reserved_types: frozenset[type] = frozenset()
        substrate_dep_markers: frozenset[type] = frozenset()

        def bind(self, runtime: Any, descriptors: Any = None) -> Any:
            return None

        def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
            return None

    try:
        SURFACE_REGISTRY.register_surface(_StubSurface())
        assert "stub_for_name_registry" in registered_surface_names()
    finally:
        SURFACE_REGISTRY._by_name.pop("stub_for_name_registry", None)
        if "stub_for_name_registry" in _REGISTERED_SURFACE_NAMES:
            _REGISTERED_SURFACE_NAMES.remove("stub_for_name_registry")
