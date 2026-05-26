"""Kernel-layer surface name registry (``a2kit._surface_names``).

Covers the ``surface-protocol`` ADDED requirement that
``SurfaceRegistry.register_surface()`` side-effects ``s.name`` into the
kernel name registry, and that the API itself is idempotent and ordered.

Per ``bootstrap-surfaces-explicit`` (2026-05-26), registration happens
at ``runtime.build()`` time rather than at import time. Tests that need
populated names build a minimal runtime first.
"""

from __future__ import annotations

from typing import Any

import a2kit
from a2kit._surface_names import (
    register_surface_name,
    registered_surface_names,
)
from a2kit.packages.dispatch.surface import SurfaceRegistry
from a2kit.runtime import build


def test_bundled_surfaces_are_registered_after_build() -> None:
    """`runtime.build()` composes the default surface pair (mcp + api),
    each `register_surface(...)` call side-effects the kernel name list.
    """
    build(a2kit.App("demo"))
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


def test_register_via_per_runtime_registry_populates_name_list() -> None:
    """Registering through a fresh ``SurfaceRegistry`` populates the
    kernel name list as a side-effect. Uses the class directly rather
    than the deprecated module-level proxy.
    """

    class _StubSurface:
        name = "stub_for_name_registry"
        reserved_types: frozenset[type] = frozenset()
        substrate_dep_markers: frozenset[type] = frozenset()

        def bind(self, runtime: Any, descriptors: Any = None) -> Any:
            return None

        def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
            return None

    fresh = SurfaceRegistry()
    fresh.register_surface(_StubSurface())
    assert "stub_for_name_registry" in registered_surface_names()
    # No cleanup of `_REGISTERED_SURFACE_NAMES` — it's an append-only set;
    # subsequent tests don't assert "stub_for_name_registry" is absent.
