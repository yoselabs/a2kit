"""``App.api`` and ``App.mcp`` lazy decorator-surface properties.

Cold-start guarantees:

- Constructing ``App`` does NOT construct either surface.
- Touching ``app.api`` does NOT pull ``fastapi``.
- Touching ``app.mcp`` does NOT pull ``fastmcp`` either — both surfaces
  are plain dataclasses; the substrate is loaded only at build/serve time.
- Repeated access returns the same instance (idempotent).

The runtime carries the touched surfaces (or ``None`` if untouched) so
``build_http_app`` / ``build_mcp_server`` can pull author-written
substrate-native registrations without an extra argument hop.
"""

from __future__ import annotations

import a2kit
from a2kit.runtime import build


def test_app_api_lazy_construction() -> None:
    app = a2kit.App("demo")
    assert app._api is None  # noqa: SLF001 -- assertion seam
    surface = app.api
    assert surface is not None
    assert app._api is surface  # noqa: SLF001
    # Idempotent: second access returns the same instance.
    assert app.api is surface


def test_app_mcp_lazy_construction() -> None:
    app = a2kit.App("demo")
    assert app._mcp is None  # noqa: SLF001
    surface = app.mcp
    assert surface is not None
    assert app._mcp is surface  # noqa: SLF001
    assert app.mcp is surface


def test_constructing_app_does_not_touch_surface_attrs() -> None:
    """Plain App() construction must not populate ``_api`` / ``_mcp``."""
    app = a2kit.App("demo")
    assert app._api is None  # noqa: SLF001
    assert app._mcp is None  # noqa: SLF001


def test_runtime_carries_touched_api_surface() -> None:
    app = a2kit.App("demo")

    @app.api.get("/v")
    async def _v() -> dict[str, str]:
        return {"v": "1"}

    runtime = build(app)
    assert runtime.api_surface is app._api  # noqa: SLF001
    assert len(runtime.api_surface.routes) == 1


def test_runtime_api_surface_is_none_when_untouched() -> None:
    app = a2kit.App("demo")
    runtime = build(app)
    assert runtime.api_surface is None
    assert runtime.mcp_surface is None


def test_runtime_carries_touched_mcp_surface() -> None:
    app = a2kit.App("demo")

    @app.mcp.tool(name="hello")
    async def _h() -> dict[str, str]:
        return {"v": "hi"}

    runtime = build(app)
    assert runtime.mcp_surface is app._mcp  # noqa: SLF001
    assert len(runtime.mcp_surface.registrations) == 1
