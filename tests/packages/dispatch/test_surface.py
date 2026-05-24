"""BDD: `Surface` Protocol + `DecoratorSurface[R]` template + `SurfaceRegistry`.

Per `add-surface-protocol-additive`. Verifies:
  - `McpSurface` and `ApiSurface` satisfy `Surface` Protocol.
  - `SURFACE_REGISTRY.register_surface` accepts and rejects duplicate names.
  - Bundled surfaces self-register at the lazy front-door load of their
    package (`a2kit.packages.mcp` / `a2kit.packages.http`).
  - `DecoratorSurface[R]` owns the registrations accumulator (subclasses
    do not redeclare it).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from a2kit.packages.dispatch.surface import (
    SURFACE_REGISTRY,
    DecoratorSurface,
    Surface,
    SurfaceRegistry,
)


class TestSurfaceProtocolSatisfaction:
    def test_mcp_surface_satisfies_protocol(self) -> None:
        from a2kit.packages.mcp.surface import McpSurface

        s = McpSurface()
        assert isinstance(s, Surface)
        assert s.name == "mcp"
        assert isinstance(s.reserved_types, frozenset)
        assert isinstance(s.substrate_dep_markers, frozenset)

    def test_api_surface_satisfies_protocol(self) -> None:
        from a2kit.packages.http.api import ApiSurface

        s = ApiSurface()
        assert isinstance(s, Surface)
        assert s.name == "api"
        assert isinstance(s.reserved_types, frozenset)
        # FastAPI surface declares Depends/Security markers.
        assert isinstance(s.substrate_dep_markers, frozenset)


class TestSurfaceRegistry:
    def test_register_and_lookup(self) -> None:
        reg = SurfaceRegistry()

        @dataclass
        class _R:
            fn: Any

        class _TestSurface(DecoratorSurface[_R]):
            name = "_test_proto_lookup"
            reserved_types: frozenset[type] = frozenset()
            substrate_dep_markers: frozenset[type] = frozenset()

            def bind(self, runtime: Any, descriptors: Any) -> Any:
                return None

            def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
                return None

        s = _TestSurface()
        reg.register_surface(s)
        assert reg.get("_test_proto_lookup") is s
        assert "_test_proto_lookup" in reg.names()

    def test_duplicate_name_rejected(self) -> None:
        reg = SurfaceRegistry()

        @dataclass
        class _R:
            fn: Any

        class _DupSurface(DecoratorSurface[_R]):
            name = "_dup"
            reserved_types: frozenset[type] = frozenset()
            substrate_dep_markers: frozenset[type] = frozenset()

            def bind(self, runtime: Any, descriptors: Any) -> Any:
                return None

            def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
                return None

        reg.register_surface(_DupSurface())
        with pytest.raises(ValueError, match="_dup"):
            reg.register_surface(_DupSurface())

    def test_get_missing_raises_keyerror(self) -> None:
        reg = SurfaceRegistry()
        with pytest.raises(KeyError):
            reg.get("nope")

    def test_bundled_surfaces_self_register(self) -> None:
        # Front-door imports trigger registration of bundled surfaces.
        import a2kit.packages.http  # noqa: F401
        import a2kit.packages.mcp  # noqa: F401

        names = SURFACE_REGISTRY.names()
        assert "mcp" in names
        assert "api" in names


class TestDecoratorSurfaceTemplateOwnsAccumulator:
    def test_mcp_and_api_inherit_registrations_field(self) -> None:
        from a2kit.packages.http.api import ApiSurface
        from a2kit.packages.mcp.surface import McpSurface

        api = ApiSurface()
        mcp = McpSurface()
        # Both surfaces expose a tuple-like `registrations` attribute
        # inherited from DecoratorSurface[R]. Empty at construction.
        assert len(api.registrations) == 0
        assert len(mcp.registrations) == 0
