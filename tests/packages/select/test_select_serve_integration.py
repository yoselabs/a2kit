"""``--select`` interaction with ``build_parent_app`` auto-mount.

Per ``surface-auto-mount`` (modified in ``add-tool-select``): the
parent app's mount decision is taken AFTER selector application.
``--select 'surface=mcp'`` zeros the FastAPI registration count, so
``/api`` does not mount — operators get a structural surface narrow
without ``--mcp-only`` ever existing.
"""

from __future__ import annotations

from typing import Any

import a2kit
from a2kit.packages.serve import build_parent_app
from a2kit.runtime import build
from a2kit.testing import app_of


def _mount_paths(parent: Any) -> set[str]:
    from starlette.routing import Mount

    return {r.path for r in parent.routes if isinstance(r, Mount)}


def _make_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def ping(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    return app_of("demo", R())


def _make_app_with_health() -> a2kit.App:
    """Mirrors a real consumer (a2web): a projection tool + a health check.

    The `@app.health_check` registration installs the synthetic `_meta.health`
    tool, which is the reason `--select surface=mcp` failed to drop `/api`.
    """

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def ping(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = app_of("demo", R())

    @app.health_check
    async def _live() -> a2kit.HealthResult:
        return a2kit.HealthResult.ok()

    return app


def test_surface_mcp_select_skips_fastapi_mount() -> None:
    runtime = build(_make_app(), select=["surface=mcp"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/mcp"}


def test_surface_api_select_skips_fastmcp_mount() -> None:
    runtime = build(_make_app(), select=["surface=api"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/api"}


def test_surface_mcp_select_drops_api_even_with_health_check() -> None:
    """Regression: a registered `@app.health_check` must NOT keep `/api` mounted
    under `--select surface=mcp`. The synthetic `_meta.health` tool narrows like
    any other tool."""
    runtime = build(_make_app_with_health(), select=["surface=mcp"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/mcp"}


def test_surface_mcp_select_narrows_source_matrix_not_just_expose() -> None:
    """The source matrix (what `build_http_app` reads) is narrowed, not only the
    derived `expose` tuple — so the two network surface builders agree."""
    from a2kit._surfaces import advertised_on, matrix_for

    runtime = build(_make_app(), select=["surface=mcp"])
    ping = next(d for d in runtime.tools() if d.name == "demo_ping")
    assert tuple(ping.expose) == ("mcp",)
    assert ping._meta is not None
    assert advertised_on(matrix_for(ping._meta.extras), "mcp") is True
    assert advertised_on(matrix_for(ping._meta.extras), "api") is False


def test_surface_mcp_select_narrows_meta_health_tool() -> None:
    """The synthetic `_meta.health` descriptor is narrowed to mcp-only."""
    from a2kit._surfaces import advertised_on, matrix_for

    runtime = build(_make_app_with_health(), select=["surface=mcp"])
    health = next(d for d in runtime.tools() if d.name == "_meta.health")
    assert tuple(health.expose) == ("mcp",)
    assert health._meta is not None
    assert advertised_on(matrix_for(health._meta.extras), "api") is False


def test_surface_api_select_drops_mcp_even_with_health_check() -> None:
    """Symmetric case: `--select surface=api` yields an api-only server."""
    runtime = build(_make_app_with_health(), select=["surface=api"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/api"}


def test_filter_to_empty_raises_value_error() -> None:
    """``--select 'verb=write'`` on a read-only App leaves no registrations."""
    import pytest

    runtime = build(_make_app(), select=["verb=write"])
    assert runtime.tools() == []
    with pytest.raises(ValueError, match="no registered surface has registrations"):
        build_parent_app(runtime)
