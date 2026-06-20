"""On-serve background services + the serve supervisor (ADR 0030).

Covers the `add-serve-services` behavior contract:

- `serve_services` round-trips App → `AppRuntime` (no-op default).
- A CLI verb dispatch starts **zero** services (serve-scoped, not dispatch-scoped).
- `_serve` hands each service a `ServeContext` carrying the bound `internal_uds`.
- The supervisor (`_supervise`) is asymmetric: a listener exiting ends serve, a
  service finishing cleanly is a non-event, a crashing service tears serve down,
  and a never-returning service does not hang shutdown.

The supervisor edges drive `_serve` with a *faked* public listener (a short
coroutine) so the tests stay transport-free; the real listeners are exercised by
`test_serve.py` / the spoke topology e2e.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import a2kit
from a2kit import ServeContext
from a2kit.packages import serve as serve_mod
from a2kit.runtime import AppRuntime, build
from a2kit.testing import app_of, client


# --------------------------------------------------------------- test apps


class _Demo(a2kit.Router):
    slug = "demo"

    @a2kit.read()
    async def echo(self, *, msg: str) -> dict[str, str]:
        return {"msg": msg}


def _di_app() -> a2kit.App:
    return app_of("svc-demo", _Demo())


# --------------------------------------------------------------- 2.3 carry


def test_serve_services_round_trip_onto_runtime() -> None:
    """The App's `serve_services` ClassVar reaches `runtime.serve_services`."""

    async def svc(ctx: ServeContext) -> None: ...

    class _K(a2kit.App):
        name = "k"
        routers = (_Demo,)
        serve_services = (svc,)

    assert build(_K()).serve_services == (svc,)


def test_serve_services_default_is_empty() -> None:
    """An App that registers none yields the empty tuple (no-op default)."""
    assert build(_di_app()).serve_services == ()


# --------------------------------------------------------------- 4.1 serve-scoped


def test_cli_verb_dispatch_starts_no_service() -> None:
    """Dispatching a verb (the CLI/dispatch path) starts zero services.

    Services are launched only by `serve_process`; a tool dispatch must not
    trigger one (the regression the lazy `Router.__aenter__` hook would cause).
    """
    ran = {"called": False}

    async def svc(ctx: ServeContext) -> None:
        ran["called"] = True

    class _K(a2kit.App):
        name = "k"
        routers = (_Demo,)
        serve_services = (svc,)

    async def go() -> None:
        async with client(_K()) as c:
            assert await c.invoke("demo_echo", msg="hi") == {"msg": "hi"}

    asyncio.run(go())
    assert ran["called"] is False


# --------------------------------------------------------------- 4.2 path exposure


@pytest.mark.asyncio
async def test_service_receives_internal_uds_none_without_spoke(monkeypatch: Any) -> None:
    """`serve` without a spoke → `ctx.internal_uds is None`, `ctx.transport` set."""
    seen: dict[str, Any] = {}

    async def svc(ctx: ServeContext) -> None:
        seen["uds"] = ctx.internal_uds
        seen["transport"] = ctx.transport

    async def _fake_listener() -> None:
        await asyncio.sleep(0.05)  # ends → serve shuts down

    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    await serve_mod._serve(build(_di_app()), transport="stdio", host="h", port=0, uds_path=None, services=(svc,), mcp_options={})
    assert seen == {"uds": None, "transport": "stdio"}


@pytest.mark.asyncio
async def test_service_receives_bound_internal_uds(tmp_path: Any, monkeypatch: Any) -> None:
    """`serve --internal-uds PATH` → the service receives `ctx.internal_uds == PATH`."""
    seen: dict[str, Any] = {}
    started = asyncio.Event()

    async def svc(ctx: ServeContext) -> None:
        seen["uds"] = ctx.internal_uds
        started.set()
        await asyncio.Event().wait()  # never returns on its own

    async def _fake_listener() -> None:
        await started.wait()  # let the service record first, then end serve

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    await serve_mod._serve(build(_di_app()), transport="http", host="h", port=0, uds_path="spoke.sock", services=(svc,), mcp_options={})
    assert seen["uds"] == "spoke.sock"


# --------------------------------------------------------------- 4.3 shared runtime


@pytest.mark.asyncio
async def test_serve_enters_one_runtime_for_listener_and_service(monkeypatch: Any) -> None:
    """Listener + service run under a single `async with runtime:` (entered once)."""
    enters: list[Any] = []
    orig = AppRuntime.__aenter__

    async def _counting(self: AppRuntime) -> Any:
        enters.append(self)
        return await orig(self)

    async def svc(ctx: ServeContext) -> None: ...

    async def _fake_listener() -> None:
        await asyncio.sleep(0.02)

    monkeypatch.setattr(AppRuntime, "__aenter__", _counting)
    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    await serve_mod._serve(build(_di_app()), transport="stdio", host="h", port=0, uds_path=None, services=(svc,), mcp_options={})
    assert len(enters) == 1


# --------------------------------------------------------------- 4.4 clean return


@pytest.mark.asyncio
async def test_service_returning_cleanly_does_not_stop_serve(monkeypatch: Any) -> None:
    """A service that returns immediately is a non-event — the listener keeps serving."""
    listener_done = asyncio.Event()

    async def svc(ctx: ServeContext) -> None:
        return  # immediate clean return (e.g. a2kay's no-spoke scheduler)

    async def _fake_listener() -> None:
        await asyncio.sleep(0.05)
        listener_done.set()

    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    await serve_mod._serve(build(_di_app()), transport="stdio", host="h", port=0, uds_path=None, services=(svc,), mcp_options={})
    assert listener_done.is_set(), "the listener was torn down by a cleanly-returning service"


# --------------------------------------------------------------- 4.5 crash


@pytest.mark.asyncio
async def test_crashing_service_tears_serve_down(monkeypatch: Any) -> None:
    """A service raising propagates out of `_serve` and cancels the listener."""

    class Boom(Exception): ...

    listener_cancelled = asyncio.Event()

    async def svc(ctx: ServeContext) -> None:
        raise Boom("scheduler exploded")

    async def _fake_listener() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            listener_cancelled.set()
            raise

    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    with pytest.raises(Boom):
        await serve_mod._serve(build(_di_app()), transport="stdio", host="h", port=0, uds_path=None, services=(svc,), mcp_options={})
    assert listener_cancelled.is_set()


# --------------------------------------------------------------- 4.6 forever loop


@pytest.mark.asyncio
async def test_forever_service_is_cancelled_without_hanging(monkeypatch: Any) -> None:
    """A never-returning service is cancelled when the listener stops — no hang."""
    svc_cancelled = asyncio.Event()

    async def svc(ctx: ServeContext) -> None:
        try:
            while True:
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            svc_cancelled.set()
            raise

    async def _fake_listener() -> None:
        await asyncio.sleep(0.05)  # ends → serve must cancel the forever service

    monkeypatch.setattr(serve_mod, "_public_listener", lambda *a, **k: _fake_listener())
    # wait_for would raise TimeoutError if `_serve` hung on the forever service.
    await asyncio.wait_for(
        serve_mod._serve(build(_di_app()), transport="stdio", host="h", port=0, uds_path=None, services=(svc,), mcp_options={}),
        timeout=5,
    )
    assert svc_cancelled.is_set()
