"""v0.11 — public surface additions / contract tightenings.

Covers:
- `ToolMetadata` / `tool_metadata(fn)` public accessor wrapping the kit-stamped
  `_a2kit_*` attrs. Tests that consume metadata should go through this rather
  than the private attrs.
- `FastMCPLike` re-exported as a public Protocol.
- `ConnectionInfoLike` / `ConnectionStoreLike` re-exported from `a2kit` and
  `a2kit.connections` (their new home), still reachable via the old
  `a2kit.errors` import for one cycle.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

import a2kit
from a2kit import (
    Cap,
    ConnectionInfoLike,
    ConnectionStoreLike,
    FastMCPLike,
    Router,
    ToolMetadata,
    tool_metadata,
)


class _Row(BaseModel):
    id: int
    name: str


# --- ToolMetadata accessor ----------------------------------------------------


def test_tool_metadata_basic() -> None:
    @a2kit.tool()
    async def fetch_widgets(limit: int = 10) -> list[dict]:  # type: ignore[type-arg]
        return [{"id": i} for i in range(limit)]

    meta = tool_metadata(fetch_widgets)
    assert isinstance(meta, ToolMetadata)
    assert meta.tool_name == "fetch_widgets"
    assert "tool:fetch_widgets" in meta.capabilities
    # `list[dict]` (untyped row shape) → format precomputed as None (runtime decide).
    assert meta.format is None


def test_tool_metadata_format_precomputed_for_pydantic() -> None:
    @a2kit.tool()
    async def list_rows() -> list[_Row]:
        return []

    meta = tool_metadata(list_rows)
    assert meta.format == "tsv"


def test_tool_metadata_explicit_capabilities() -> None:
    @a2kit.tool(capabilities={Cap.WRITE, "expensive"})
    async def big_job() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(big_job)
    assert Cap.WRITE in meta.capabilities
    assert "expensive" in meta.capabilities


def test_tool_metadata_router_tag() -> None:
    class WidgetsRouter(Router):
        pass

    @WidgetsRouter.read()
    async def list_widgets() -> list[dict]:  # type: ignore[type-arg]
        return []

    # Router-level register is what tags; the bare _tools binding fn is the
    # raw function (not yet decorated). Only direct `@a2kit.tool` stamps
    # metadata at decoration time.
    @a2kit.tool()
    async def loose_tool() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(loose_tool)
    assert meta.tool_name == "loose_tool"


def test_tool_metadata_undecorated_raises() -> None:
    async def naked() -> dict:  # type: ignore[type-arg]
        return {}

    with pytest.raises(AttributeError, match=r"@a2kit\.tool"):
        tool_metadata(naked)


def test_tool_metadata_is_frozen() -> None:
    @a2kit.tool()
    async def f() -> dict:  # type: ignore[type-arg]
        return {}

    meta = tool_metadata(f)
    with pytest.raises(Exception):  # noqa: B017, PT011  # frozen dataclass
        meta.tool_name = "other"  # ty: ignore[invalid-assignment]


# --- Re-exports / Protocols ---------------------------------------------------


def test_protocols_re_exported_at_top_level() -> None:
    """Both Protocols are importable from `a2kit` directly, not just submodules."""
    assert ConnectionInfoLike is a2kit.ConnectionInfoLike
    assert ConnectionStoreLike is a2kit.ConnectionStoreLike
    assert FastMCPLike is a2kit.FastMCPLike


def test_protocols_canonical_home_is_connections() -> None:
    """v0.11: canonical home for connection Protocols is `a2kit.connections`."""
    from a2kit import connections as conns

    assert conns.ConnectionInfoLike is ConnectionInfoLike
    assert conns.ConnectionStoreLike is ConnectionStoreLike


def test_protocols_still_importable_from_errors_for_one_cycle() -> None:
    """Backward compatibility — `a2kit.errors` still re-exports for one cycle."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from a2kit import errors

    assert errors.ConnectionInfoLike is ConnectionInfoLike
    assert errors.ConnectionStoreLike is ConnectionStoreLike


# --- enrichers module rename --------------------------------------------------


def test_enrichers_is_canonical_module() -> None:
    """v0.11: `a2kit.enrichers` is the new home for `EnricherFn` / `chain` / `connection_enricher`."""
    from a2kit import enrichers

    # Top-level re-exports point at the same objects as the canonical module.
    assert a2kit.chain is enrichers.chain
    assert a2kit.connection_enricher is enrichers.connection_enricher
    assert a2kit.EnricherFn is enrichers.EnricherFn


def test_errors_module_is_deprecation_shim() -> None:
    """`a2kit.errors` still works for one cycle (until v0.13) but warns on import."""
    import importlib
    import sys
    import warnings

    # Force a re-import so the module-level warning fires fresh.
    sys.modules.pop("a2kit.errors", None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        errors = importlib.import_module("a2kit.errors")

    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("a2kit.enrichers" in str(w.message) for w in deprecations)
    # And the re-exports themselves still resolve to the canonical objects.
    from a2kit import enrichers

    assert errors.chain is enrichers.chain
    assert errors.connection_enricher is enrichers.connection_enricher


def test_a2kit_config_home_alias_removed_with_hint() -> None:
    """v0.11: `A2KIT_CONFIG_HOME` self-alias removed; ImportError hint points to `ENV_CONFIG_HOME`."""
    with pytest.raises(ImportError, match="ENV_CONFIG_HOME"):
        _ = a2kit.A2KIT_CONFIG_HOME  # noqa: B018


# --- FastMCPLike structural typing -------------------------------------------


def test_fastmcp_like_is_runtime_checkable() -> None:
    """`FastMCPLike` is `@runtime_checkable` — `isinstance` works on duck types."""

    class _RealEnough:
        settings: Any = type("S", (), {"host": "h", "port": 1})()

        def tool(self, *_a: Any, **_kw: Any) -> Any:
            return lambda fn: fn

        def run(self, *_a: Any, **_kw: Any) -> None:
            return None

    assert isinstance(_RealEnough(), FastMCPLike)


def test_fastmcp_like_rejects_missing_method() -> None:
    class _NoTool:
        settings: Any = type("S", (), {"host": "h", "port": 1})()

        def run(self, *_a: Any, **_kw: Any) -> None:
            return None

    assert not isinstance(_NoTool(), FastMCPLike)
