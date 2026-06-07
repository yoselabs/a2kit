"""``expose=`` and ``authorize=`` kwargs on ``@a2kit.read/list/write``.

Per ``verb-decorators`` ADDED requirements (add-multi-surface) and
``bootstrap-surfaces-explicit`` (2026-05-26):

- Default ``expose=("mcp", "api")``.
- Empty tuple raises ``ValueError`` at decoration time (a tool exposed
  on no substrate is dead code).
- Unknown surface names raise ``TypeError`` at **runtime.build()**
  time (NOT at decoration), per ``bootstrap-surfaces-explicit``:
  surface validation requires the composed registry, which is built
  at ``runtime.build(surfaces=...)`` time.
- ``authorize`` is the per-tool auth callable; surface stamped here,
  enforcement lands in ``add-auth``.
- Values land on ``ToolDescriptor.expose`` / ``.authorize`` / ``.verb``
  so substrate adapters and selectors don't have to re-read
  ``A2KitMeta``.
"""

from __future__ import annotations

from typing import Any

import pytest

import a2kit
from a2kit.metadata import _get_meta
from a2kit.runtime import build


class _Tag:
    v = "ok"


def _build(verb_decorator: Any, **extra: Any) -> a2kit.App:
    class R(a2kit.Router):
        slug = "demo"

        @verb_decorator(**extra)
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    return a2kit.App("demo").add_router(R())


def test_default_expose_is_both_substrates() -> None:
    app = _build(a2kit.read)
    runtime = build(app)
    [desc] = runtime.tools()
    assert desc.expose == ("mcp", "api")
    assert desc.authorize is None
    assert desc.verb == "read"


def test_expose_mcp_only() -> None:
    app = _build(a2kit.read, expose=("mcp",))
    runtime = build(app)
    [desc] = runtime.tools()
    assert desc.expose == ("mcp",)


def test_expose_api_only() -> None:
    app = _build(a2kit.write, expose=("api",))
    runtime = build(app)
    [desc] = runtime.tools()
    assert desc.expose == ("api",)
    assert desc.verb == "write"


def test_empty_expose_raises_at_decoration() -> None:
    with pytest.raises(ValueError, match="at least one surface"):

        class R(a2kit.Router):
            slug = "demo"

            @a2kit.read(expose=())
            async def t(self, *, k: str) -> dict[str, str]:
                return {"k": k}


def test_unknown_substrate_raises_at_build() -> None:
    """Per `bootstrap-surfaces-explicit`: unknown surface in expose= is
    a build-time error, not a decoration-time error. The decorator
    captures expose= unchanged; build() walks descriptors and validates
    against the composed surface registry passed via `surfaces=`.
    """

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("mcp", "graphql"))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    surfaces = a2kit.compose_default_surfaces()
    with pytest.raises(TypeError, match="unknown surface"):
        build(app, surfaces=surfaces)


def test_unknown_surface_error_enumerates_registered_names() -> None:
    """Per `bootstrap-surfaces-explicit`: the build-time error lists the
    composed surface set, not a hardcoded literal.
    """

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("zzz",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    surfaces = a2kit.compose_default_surfaces()
    with pytest.raises(TypeError) as exc:
        build(app, surfaces=surfaces)

    msg = str(exc.value)
    # Default surfaces = (McpSurface(), ApiSurface()) → names "mcp", "api"
    for name in ("mcp", "api"):
        assert name in msg, f"expected composed surface {name!r} in error: {msg!r}"


def test_newly_registered_surface_name_is_accepted_via_explicit_surfaces() -> None:
    """Per `bootstrap-surfaces-explicit`: registering a synthetic Surface
    is done by passing it via `build(app, surfaces=(...))`, not by
    mutating a module-level registry. The decorator captures the name
    unchanged; build accepts it when the composed surface set includes it.
    """

    class _StubSurface:
        name = "stub_expose"
        reserved_types: frozenset[type] = frozenset()
        substrate_dep_markers: frozenset[type] = frozenset()

        def bind(self, runtime: Any, descriptors: Any = None) -> Any:
            return None

        def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
            return None

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("stub_expose",))  # type: ignore[arg-type]
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    # Build with the custom surface explicitly included alongside defaults.
    from a2kit.packages.dispatch.surface import SurfaceRegistry
    from a2kit.packages.http.api import ApiSurface
    from a2kit.packages.mcp.surface import McpSurface

    registry = SurfaceRegistry()
    for s in (McpSurface(), ApiSurface(), _StubSurface()):
        registry.register_surface(s)

    runtime = build(app, surfaces=registry)
    [desc] = runtime.tools()
    assert desc.expose == ("stub_expose",)
    # Meta still carries the captured value too.
    meta = _get_meta(R.t)
    assert meta is not None
    assert meta.extras.expose == ("stub_expose",)


def test_empty_surfaces_skips_validation() -> None:
    """Per `bootstrap-surfaces-explicit`: when an EMPTY `SurfaceRegistry`
    is passed explicitly (no surfaces composed at all), validation is
    skipped — the author has opted out of the registered set, and there's
    nothing to validate against.
    """
    from a2kit.packages.dispatch.surface import SurfaceRegistry

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("mcp",))
        async def t(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    app = a2kit.App("demo").add_router(R())
    empty_registry = SurfaceRegistry()
    runtime = build(app, surfaces=empty_registry)
    [desc] = runtime.tools()
    assert desc.expose == ("mcp",)  # Captured unchanged; no surface to project on.


def test_authorize_callable_lands_on_descriptor() -> None:
    async def _gate(*_: Any, **__: Any) -> bool:
        return True

    app = _build(a2kit.read, authorize=_gate)
    runtime = build(app)
    [desc] = runtime.tools()
    assert desc.authorize is _gate


def test_list_decorator_carries_expose_and_authorize() -> None:
    async def _gate(*_: Any, **__: Any) -> bool:
        return True

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.list_("k", expose=("mcp",), authorize=_gate)
        async def items(self, *, q: str) -> list[dict[str, str]]:
            return [{"k": q}]

    runtime = build(a2kit.App("demo").add_router(R()))
    [desc] = runtime.tools()
    assert desc.verb == "list"
    assert desc.expose == ("mcp",)
    assert desc.authorize is _gate


def test_meta_extras_carry_expose_and_authorize() -> None:
    """``A2KitMeta.extras`` is the storage; descriptor reads from it."""

    async def _gate() -> bool:
        return True

    @a2kit.read(expose=("api",), authorize=_gate)
    async def fetch(*, id: str) -> dict[str, str]:
        return {"id": id}

    meta = _get_meta(fetch)
    assert meta is not None
    assert meta.extras.expose == ("api",)
    assert meta.extras.authorize is _gate


def test_http_build_filters_by_expose() -> None:
    """A projection tool with expose=('mcp',) does NOT mount on /api."""
    from fastapi.testclient import TestClient

    from a2kit.packages.http import build_http_app

    class R(a2kit.Router):
        slug = "demo"

        @a2kit.read(expose=("mcp",))
        async def mcp_only(self, *, k: str) -> dict[str, str]:
            return {"k": k}

        @a2kit.read(expose=("api",))
        async def api_only(self, *, k: str) -> dict[str, str]:
            return {"k": k}

    runtime = build(a2kit.App("demo").add_router(R()))
    import asyncio

    async def _exercise() -> None:
        async with runtime:
            api = build_http_app(runtime)
            with TestClient(api) as client:
                # api-only registered
                r = client.post("/api_only", json={"k": "x"})
                assert r.status_code == 200
                # mcp-only filtered out
                r = client.post("/mcp_only", json={"k": "x"})
                assert r.status_code == 404

    asyncio.run(_exercise())
