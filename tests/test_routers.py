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
        name = "rprov"
        providers = (_ServiceA, _ServiceB)

    app = a2kit.App("t")
    app.add_router(_R())
    assert app.has_provider(_ServiceA)
    assert app.has_provider(_ServiceB)


def test_router_providers_with_explicit_factory_tuple() -> None:
    class _R(Router):
        name = "rfac"
        providers = ((_ServiceA, _ServiceA),)

    app = a2kit.App("t")
    app.add_router(_R())
    assert app.has_provider(_ServiceA)


def test_router_lifecycle_hooks_fire() -> None:
    import anyio

    calls: list[str] = []

    class _R(Router):
        name = "rlife"

        async def on_startup(self) -> None:
            calls.append("up")

        async def on_shutdown(self) -> None:
            calls.append("down")

    app = a2kit.App("t")
    app.add_router(_R())

    from a2kit.app import dispatch_shutdown, dispatch_startup

    async def _go() -> None:
        await dispatch_startup(app)
        await dispatch_shutdown(app)

    anyio.run(_go)
    assert calls == ["up", "down"]


def test_plain_router_unchanged() -> None:
    """Router without providers/lifecycle still works as before."""

    class _R(Router):
        name = "rplain"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"k": 1}

    app = a2kit.App("t")
    app.add_router(_R())
    assert any(r.slug == "rplain" for r in app.routers())
