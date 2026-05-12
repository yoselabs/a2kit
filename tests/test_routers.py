"""Mirror tests for ``a2kit.routers``."""

from __future__ import annotations

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
    from contextlib import asynccontextmanager

    closed: list[str] = []

    class _Good(Router):
        slug = "good"
        tools = ()

        @asynccontextmanager
        async def lifespan(self):
            closed.append("good-enter")
            try:
                yield
            finally:
                closed.append("good-exit")

    class _Bad(Router):
        slug = "bad"
        tools = ()

        @asynccontextmanager
        async def lifespan(self):
            raise RuntimeError("boom")
            yield  # unreachable

    app = a2kit.App("t")
    app.add_router(_Good())
    app.add_router(_Bad())

    from a2kit.app import dispatch_startup

    async def _go() -> None:
        import contextlib

        with contextlib.suppress(RuntimeError):
            await dispatch_startup(app)

    anyio.run(_go)
    # Good lifespan entered, then unwound when Bad raised.
    assert "good-enter" in closed
    assert "good-exit" in closed


def test_router_lifespan_post_yield_raise_logged_and_continues() -> None:
    import anyio
    from contextlib import asynccontextmanager

    class _R(Router):
        slug = "shutdown_raise"
        tools = ()

        @asynccontextmanager
        async def lifespan(self):
            yield
            raise RuntimeError("shutdown boom")

    app = a2kit.App("t")
    app.add_router(_R())

    from a2kit.app import dispatch_shutdown, dispatch_startup

    async def _go() -> None:
        await dispatch_startup(app)
        # Shutdown should swallow the exception and log it.
        await dispatch_shutdown(app)

    anyio.run(_go)


def test_router_lifespan_composes_into_app_lifecycle() -> None:
    import anyio
    from contextlib import asynccontextmanager

    calls: list[str] = []

    class _R(Router):
        slug = "rlife"
        tools = ()

        @asynccontextmanager
        async def lifespan(self):
            calls.append("up")
            try:
                yield
            finally:
                calls.append("down")

    app = a2kit.App("t")
    app.add_router(_R())

    from a2kit.app import dispatch_shutdown, dispatch_startup

    async def _go() -> None:
        await dispatch_startup(app)
        await dispatch_shutdown(app)

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


def test_decorated_method_not_in_tuple_is_not_registered() -> None:
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
    app.add_router(_R())
    tool_names = {getattr(fn, "__name__", "") for fn in app.tools()}
    assert "listed" in tool_names
    assert "unlisted" not in tool_names


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
