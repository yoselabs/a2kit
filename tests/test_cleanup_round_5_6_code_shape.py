"""Tests — cleanup-round-5-6-code-shape bundle.

Covers items A (LDD ctx binding consistency) and B (Container._override).
F (shorthand error fidelity) is exercised in test_ambient_ldd_ctx.py.
Item L (WARN_ONCE on docstring failures) was removed in v0.30.0 along
with the docstring-pull feature itself.
"""

from __future__ import annotations

import asyncio

import pytest

import a2kit
from a2kit.exceptions import AmbientContextMissing
from a2kit.ldd import event as ldd_event
from a2kit.packages.di.container import Container


# --- A. LDD ctx binding consistency — CLI + TestClient must not synthesize --- #


class _NoCtxRouter(a2kit.Router):
    @a2kit.read()
    async def ping(self) -> dict[str, str]:
        await ldd_event("from-no-ctx-tool")
        return {"ok": "yes"}


def test_test_client_no_ctx_tool_raises_on_ldd_primitive() -> None:
    """TestClient must not synthesize a capturing ctx for a no-ctx tool."""
    from a2kit.testing import client

    app = a2kit.App("noctx").add_router(_NoCtxRouter())

    async def go() -> None:
        async with client(app) as c:
            with pytest.raises(AmbientContextMissing):
                await c.invoke("ping")

    asyncio.run(go())


def test_cli_runtime_no_ctx_tool_raises_on_ldd_primitive() -> None:
    """CLI runtime must not synthesize a StderrToolContext for a no-ctx tool."""
    from a2kit.packages.cli.runtime import invoke_tool_sync

    async def tool_body() -> dict[str, str]:
        await ldd_event("x")
        return {"ok": "yes"}

    with pytest.raises(AmbientContextMissing):
        invoke_tool_sync(tool_body, {}, ctx_param_name=None)


# --- B. Container._override --- #


class _Greeter:
    def __init__(self) -> None:
        self.name = "real"

    def hello(self) -> str:
        return f"hello from {self.name}"


def test_override_pins_singleton() -> None:
    c = Container()
    c.register_singleton(_Greeter, _Greeter)
    fake = _Greeter()
    fake.name = "fake"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake


def test_override_pins_per_call_provider() -> None:
    c = Container()
    c.register(_Greeter)
    fake = _Greeter()
    fake.name = "override"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake


def test_override_clears_async_factory_marker() -> None:
    c = Container()

    async def afactory() -> _Greeter:
        return _Greeter()

    c.register_singleton(_Greeter, afactory)
    assert c.has_async_singleton(_Greeter)
    fake = _Greeter()
    c._override(_Greeter, fake)
    assert not c.has_async_singleton(_Greeter)
    # Sync resolve no longer raises now that the marker is cleared.
    assert c.resolve(_Greeter) is fake


def test_override_then_restore_returns_to_pre_snapshot_state() -> None:
    c = Container()
    c.register(_Greeter)
    snapshot = c._snapshot()
    fake = _Greeter()
    fake.name = "fake"
    c._override(_Greeter, fake)
    assert c.resolve(_Greeter) is fake
    c._restore(snapshot)
    fresh = c.resolve(_Greeter)
    assert fresh is not fake
    assert fresh.name == "real"
