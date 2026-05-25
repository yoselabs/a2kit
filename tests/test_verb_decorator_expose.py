"""``expose=`` and ``authorize=`` kwargs on ``@a2kit.read/list/write``.

Per ``verb-decorators`` ADDED requirements (add-multi-surface):

- Default ``expose=("mcp", "api")``.
- Empty tuple raises ``ValueError`` at decoration time (a tool exposed
  on no substrate is dead code).
- Unknown substrate names raise ``TypeError`` (per
  ``surface-set-from-registry``) enumerating the registered names.
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

        tools = (t,)

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

            tools = (t,)


def test_unknown_substrate_raises() -> None:
    with pytest.raises(TypeError, match="unknown surface"):

        class R(a2kit.Router):
            slug = "demo"

            @a2kit.read(expose=("mcp", "graphql"))  # type: ignore[arg-type]
            async def t(self, *, k: str) -> dict[str, str]:
                return {"k": k}

            tools = (t,)


def test_unknown_surface_error_enumerates_registered_names() -> None:
    """``surface-set-from-registry``: the error lists the live registry,
    not a hardcoded literal.
    """
    from a2kit._surface_names import registered_surface_names

    registered = registered_surface_names()
    with pytest.raises(TypeError) as exc:

        class R(a2kit.Router):
            slug = "demo"

            @a2kit.read(expose=("zzz",))  # type: ignore[arg-type]
            async def t(self, *, k: str) -> dict[str, str]:
                return {"k": k}

            tools = (t,)

    msg = str(exc.value)
    for name in registered:
        assert name in msg, f"expected registered surface {name!r} in error: {msg!r}"


def test_newly_registered_surface_name_is_accepted_without_verb_edits() -> None:
    """Spec scenario: registering a synthetic Surface makes its name
    valid in ``expose=`` with no edits to ``_verbs.py``.
    """
    from a2kit._surface_names import _REGISTERED_SURFACE_NAMES
    from a2kit.packages.dispatch import SURFACE_REGISTRY

    class _StubSurface:
        name = "stub_expose"
        reserved_types: frozenset[type] = frozenset()
        substrate_dep_markers: frozenset[type] = frozenset()

        def bind(self, runtime: Any, descriptors: Any = None) -> Any:
            return None

        def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
            return None

    try:
        SURFACE_REGISTRY.register_surface(_StubSurface())

        class R(a2kit.Router):
            slug = "demo"

            @a2kit.read(expose=("stub_expose",))  # type: ignore[arg-type]
            async def t(self, *, k: str) -> dict[str, str]:
                return {"k": k}

            tools = (t,)

        meta = _get_meta(R.t)
        assert meta is not None
        assert meta.extras.expose == ("stub_expose",)
    finally:
        SURFACE_REGISTRY._by_name.pop("stub_expose", None)
        if "stub_expose" in _REGISTERED_SURFACE_NAMES:
            _REGISTERED_SURFACE_NAMES.remove("stub_expose")


def test_empty_registry_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec scenario: with no surfaces registered, validation raises
    ``TypeError`` and the message points the author at the bundled
    surface-mounting packages.
    """
    from a2kit import _surface_names

    monkeypatch.setattr(_surface_names, "_REGISTERED_SURFACE_NAMES", [])

    with pytest.raises(TypeError, match="no surfaces registered"):

        class R(a2kit.Router):
            slug = "demo"

            @a2kit.read(expose=("mcp",))
            async def t(self, *, k: str) -> dict[str, str]:
                return {"k": k}

            tools = (t,)


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

        tools = (items,)

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

        tools = (mcp_only, api_only)

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
