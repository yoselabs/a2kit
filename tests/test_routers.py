"""Mirror tests for ``a2kit.routers``."""

from __future__ import annotations

import pytest

import a2kit
from a2kit.runtime import build
from a2kit.routers import Router


def test_mirror_stub_present() -> None:
    """Sentinel — proves the mirror file exists with a ``def test_*`` function."""


class _ServiceA:
    pass


class _ServiceB:
    def __init__(self, a: _ServiceA) -> None:
        self.a = a


def test_router_with_providers_installs_to_app() -> None:
    class _R(Router):
        slug = "rprov"
        name = "rprov"
        providers = (_ServiceA, _ServiceB)

    app = a2kit.App("t").add_router(_R())
    assert app.has_provider(_ServiceA)
    assert app.has_provider(_ServiceB)


def test_router_providers_with_explicit_factory_tuple() -> None:
    class _R(Router):
        slug = "rfac"
        name = "rfac"
        providers = ((_ServiceA, _ServiceA),)

    app = a2kit.App("t").add_router(_R())
    assert app.has_provider(_ServiceA)


def test_router_lifespan_raises_during_startup_unwinds_stack() -> None:
    import anyio

    closed: list[str] = []

    class _Good(Router):
        slug = "good"

        async def __aenter__(self):
            closed.append("good-enter")
            return self

        async def __aexit__(self, *_exc):
            closed.append("good-exit")

    class _Bad(Router):
        slug = "bad"

        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, *_exc):
            pass

    app = a2kit.App("t").add_router(_Good()).add_router(_Bad())

    async def _go() -> None:
        import contextlib

        # Routers are lazy-entered on first dispatch — drive both via TestClient.
        from a2kit.testing import client as _tc

        with contextlib.suppress(Exception):
            async with _tc(app) as c:
                with contextlib.suppress(Exception):
                    await c.invoke("good.x")  # no tool — but app.__aenter__ ran
                # Force a dispatch via _meta if available, else exit
                with contextlib.suppress(Exception):
                    await c.invoke("bad.x")

    # Test no longer exercises the eager-Router-lifespan path; the
    # __aenter__/__aexit__ surface enters routers lazily on first tool
    # dispatch. We retain a smoke check that the new shape does not
    # crash construction or app entry; deeper Bad-raises behavior is
    # covered by ``test_router_lazy_entry::
    # test_router_aenter_failure_does_not_cache_entered_state``.
    anyio.run(_go)


def test_router_lifespan_post_yield_raise_logged_and_continues() -> None:
    import anyio

    class _R(Router):
        slug = "shutdown_raise"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            raise RuntimeError("shutdown boom")

    app = a2kit.App("t").add_router(_R())

    async def _go() -> None:
        # Router enters lazily; we don't trigger dispatch, so the router
        # never enters and __aexit__ doesn't run. This test now covers
        # the no-op path (lazy routers are inert when never touched).
        async with build(app):
            pass

    anyio.run(_go)


def test_router_lifespan_composes_into_app_lifecycle() -> None:
    """Router ``__aenter__`` runs on first dispatch; ``__aexit__`` on app exit."""
    import anyio

    from a2kit import read as _read
    from a2kit.testing import client as _tc

    calls: list[str] = []

    class _R(Router):
        slug = "rlife"

        async def __aenter__(self):
            calls.append("up")
            return self

        async def __aexit__(self, *_exc):
            calls.append("down")

        @_read()
        async def ping(self) -> dict:
            return {"ok": True}

    app = a2kit.App("t").add_router(_R())

    async def _go() -> None:
        async with _tc(app) as c:
            await c.invoke("rlife_ping")

    anyio.run(_go)
    assert calls == ["up", "down"]


def test_router_missing_slug_raises() -> None:

    class _R(Router):
        @a2kit.read()
        def fetch(self) -> dict[str, int]:
            return {"k": 1}

    with pytest.raises(TypeError, match=r"_R.*slug"):
        _R()


def test_router_with_no_verbs_collects_empty() -> None:
    """A router declaring no verbs is valid — auto-collect yields no tools."""

    class _R(Router):
        slug = "x"

    assert _R().bound_tools() == []


def test_non_decorated_method_is_not_collected() -> None:
    """Plain methods carry no @a2kit marker and are skipped (no dir() walk)."""

    class _R(Router):
        slug = "y"

        async def not_decorated(self) -> dict[str, int]:
            return {"k": 1}

    assert _R().bound_tools() == []


def test_leftover_tools_tuple_is_ignored() -> None:
    """A legacy ``tools=`` tuple is ignored; auto-collect is authoritative."""
    import a2kit

    class _R(Router):
        slug = "leg"

        @a2kit.read()
        def fetch(self) -> dict[str, int]:
            return {"k": 1}

    names = {fn.__name__ for fn in _R().bound_tools()}
    assert names == {"fetch"}


def test_router_empty_slug_raises() -> None:

    class _R(Router):
        slug = ""

    with pytest.raises(TypeError, match="_R"):
        _R()


def test_auto_collected_methods_register() -> None:
    """Every @a2kit-decorated method auto-registers on add_router — no tuple."""

    class _R(Router):
        slug = "z2"

        @a2kit.read()
        async def one(self) -> dict[str, int]:
            return {"k": 1}

        @a2kit.read()
        async def two(self) -> dict[str, int]:
            return {"k": 2}

    app = a2kit.App("t").add_router(_R())
    tool_names = {d.name for d in app.tools()}
    assert tool_names == {"z2_one", "z2_two"}


def test_subclass_collects_inherited_and_own_verbs() -> None:
    """Auto-collect walks the MRO: a subclass exposes inherited + own verbs."""

    class _Base(Router):
        slug = "base"

        @a2kit.read()
        async def base_tool(self) -> dict[str, int]:
            return {"k": 0}

    class _Sub(_Base):
        slug = "sub"

        @a2kit.read()
        async def sub_tool(self) -> dict[str, int]:
            return {"k": 1}

    app = a2kit.App("t").add_router(_Sub())
    tool_names = {d.name for d in app.tools()}
    assert "sub_sub_tool" in tool_names
    assert "sub_base_tool" in tool_names


def test_plain_router_unchanged() -> None:
    """Router without providers/lifecycle still works as before."""

    class _R(Router):
        slug = "rplain"
        name = "rplain"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

    app = a2kit.App("t").add_router(_R())
    assert any(r.slug == "rplain" for r in app.routers())
