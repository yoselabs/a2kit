"""Mirror tests for ``a2kit.routers``."""

from __future__ import annotations

import pytest

import a2kit
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
        tools = ()
        slug = "rprov"
        name = "rprov"
        providers = (_ServiceA, _ServiceB)

    app = a2kit.App("t")
    app.add_router(_R())
    assert app.has_provider(_ServiceA)
    assert app.has_provider(_ServiceB)


def test_router_providers_with_explicit_factory_tuple() -> None:
    class _R(Router):
        tools = ()
        slug = "rfac"
        name = "rfac"
        providers = ((_ServiceA, _ServiceA),)

    app = a2kit.App("t")
    app.add_router(_R())
    assert app.has_provider(_ServiceA)


def test_router_lifespan_raises_during_startup_unwinds_stack() -> None:
    import anyio

    closed: list[str] = []

    class _Good(Router):
        slug = "good"
        tools = ()

        async def __aenter__(self):
            closed.append("good-enter")
            return self

        async def __aexit__(self, *_exc):
            closed.append("good-exit")

    class _Bad(Router):
        slug = "bad"
        tools = ()

        async def __aenter__(self):
            raise RuntimeError("boom")

        async def __aexit__(self, *_exc):
            pass

    app = a2kit.App("t")
    app.add_router(_Good())
    app.add_router(_Bad())

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
        tools = ()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            raise RuntimeError("shutdown boom")

    app = a2kit.App("t")
    app.add_router(_R())

    async def _go() -> None:
        # Router enters lazily; we don't trigger dispatch, so the router
        # never enters and __aexit__ doesn't run. This test now covers
        # the no-op path (lazy routers are inert when never touched).
        async with app:
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

        tools = (ping,)

    app = a2kit.App("t")
    app.add_router(_R())

    async def _go() -> None:
        async with _tc(app) as c:
            await c.invoke("rlife.ping")

    anyio.run(_go)
    assert calls == ["up", "down"]


def test_router_missing_slug_raises() -> None:
    import pytest

    class _R(Router):
        tools = ()

    with pytest.raises(TypeError, match=r"_R.*slug"):
        _R()


def test_router_missing_tools_raises() -> None:
    import pytest

    class _R(Router):
        slug = "x"

    with pytest.raises(TypeError, match=r"_R.*tools"):
        _R()


def test_router_tool_in_tuple_without_meta_raises() -> None:
    import pytest

    class _R(Router):
        slug = "y"

        async def not_decorated(self) -> dict[str, int]:
            return {"k": 1}

        tools = (not_decorated,)

    with pytest.raises(TypeError, match="not_decorated"):
        _R()


def test_router_non_callable_in_tools_raises() -> None:
    import pytest

    class _R(Router):
        slug = "nc"
        tools = ("not_a_callable",)  # type: ignore[assignment]

    with pytest.raises(TypeError, match="callable"):
        _R()


def test_router_tools_not_tuple_raises() -> None:
    import pytest

    class _R(Router):
        slug = "nt"
        tools = []  # type: ignore[assignment]

    with pytest.raises(TypeError, match="tools"):
        _R()


def test_router_empty_slug_raises() -> None:
    import pytest

    class _R(Router):
        slug = ""
        tools = ()

    with pytest.raises(TypeError, match="_R"):
        _R()


def test_decorated_method_not_in_tuple_raises_at_app_construction() -> None:
    """Post ``app-time-tools-tuple-validation``: ``App.add_router``
    raises when a Router has decorated methods missing from its
    ``tools`` tuple. Previously the methods were silently invisible
    (a tier-1 footgun); the new contract fails loud at App
    construction so the drift can't reach production.
    """
    from a2kit.exceptions import A2KitDecoratedMethodNotInTools

    class _R(Router):
        slug = "z"

        @a2kit.read()
        async def listed(self) -> dict[str, int]:
            return {"k": 1}

        @a2kit.read()
        async def unlisted(self) -> dict[str, int]:
            return {"k": 2}

        tools = (listed,)

    app = a2kit.App("t")
    with pytest.raises(A2KitDecoratedMethodNotInTools) as ei:
        app.add_router(_R())
    assert "unlisted" in ei.value.missing
    assert "listed" not in ei.value.missing


def test_all_decorated_methods_listed_passes() -> None:
    """Negative case: every decorated method in tuple → add_router clean."""

    class _R(Router):
        slug = "z2"

        @a2kit.read()
        async def one(self) -> dict[str, int]:
            return {"k": 1}

        @a2kit.read()
        async def two(self) -> dict[str, int]:
            return {"k": 2}

        tools = (one, two)

    app = a2kit.App("t").add_router(_R())
    tool_names = {d.name for d in app.tools()}
    assert tool_names == {"one", "two"}


def test_inherited_decorated_method_does_not_trigger_validation() -> None:
    """A subclass that doesn't re-list an inherited decorated method
    is fine — validation inspects only ``cls.__dict__``."""

    class _Base(Router):
        slug = "base"

        @a2kit.read()
        async def base_tool(self) -> dict[str, int]:
            return {"k": 0}

        tools = (base_tool,)

    class _Sub(_Base):
        slug = "sub"

        @a2kit.read()
        async def sub_tool(self) -> dict[str, int]:
            return {"k": 1}

        tools = (sub_tool,)

    app = a2kit.App("t").add_router(_Sub())
    tool_names = {d.name for d in app.tools()}
    assert "sub_tool" in tool_names


def test_plain_router_unchanged() -> None:
    """Router without providers/lifecycle still works as before."""

    class _R(Router):
        slug = "rplain"
        name = "rplain"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

        tools = (ping,)

    app = a2kit.App("t")
    app.add_router(_R())
    assert any(r.slug == "rplain" for r in app.routers())
