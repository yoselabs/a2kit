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


def _mount_paths(parent: Any) -> set[str]:
    from starlette.routing import Mount

    return {r.path for r in parent.routes if isinstance(r, Mount)}


def _make_app() -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read()
        async def ping(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    return a2kit.App("demo").add_router(R())


def test_surface_mcp_select_skips_fastapi_mount() -> None:
    runtime = build(_make_app(), select=["surface=mcp"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/mcp"}


def test_surface_api_select_skips_fastmcp_mount() -> None:
    runtime = build(_make_app(), select=["surface=api"])
    parent = build_parent_app(runtime)
    assert _mount_paths(parent) == {"/api"}


def test_filter_to_empty_raises_value_error() -> None:
    """``--select 'verb=write'`` on a read-only App leaves no registrations."""
    import pytest

    runtime = build(_make_app(), select=["verb=write"])
    assert runtime.tools() == []
    with pytest.raises(ValueError, match="no registered surface has registrations"):
        build_parent_app(runtime)
