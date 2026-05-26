"""BDD: ``Container.call_scope`` per-call dispatch helper.

Covers spec ``di-per-call-scope`` §4.4-§4.5: the framework's per-tool
dispatch path opens a child resolver, resolves kwargs (Lazy[T] + eager),
runs the tool body inside the child's lifetime, and unwinds per-call
cleanup with exception preservation.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import a2kit
from a2kit.runtime import build
from a2kit.packages.di import Lazy


class _Tx:
    instances_created: int = 0
    cleanup_count: int = 0
    last_exc: BaseException | None = None

    def __init__(self) -> None:
        type(self).instances_created += 1

    async def __aenter__(self) -> _Tx:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object) -> None:
        type(self).cleanup_count += 1
        type(self).last_exc = exc


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Tx.instances_created = 0
    _Tx.cleanup_count = 0
    _Tx.last_exc = None


@pytest.mark.asyncio
async def test_dispatch_yields_resolved_kwargs() -> None:
    """``call_scope(fn, wire)`` yields merged resolved + wire kwargs."""
    app = a2kit.App("test")
    app.provide(_Tx, per_call=True)

    async def tool(tx: _Tx, name: str) -> str:
        return f"{name}:{type(tx).__name__}"

    async with build(app) as app, app._resolver.call_scope(tool, {"name": "alice"}) as kw:
        result = await tool(**kw)

    assert result == "alice:_Tx"
    assert _Tx.instances_created == 1
    assert _Tx.cleanup_count == 1


@pytest.mark.asyncio
async def test_dispatch_lazy_param_skips_unused() -> None:
    """Lazy[T] tool params yield a closure; never invoked = T never built."""
    app = a2kit.App("test")
    app.provide(_Tx, per_call=True)

    async def tool(tx: Lazy[_Tx], flag: bool) -> str:
        if flag:
            await tx()
        return "ok"

    async with build(app) as app, app._resolver.call_scope(tool, {"flag": False}) as kw:
        result = await tool(**kw)

    assert result == "ok"
    assert _Tx.instances_created == 0, "Lazy[T] resolved despite not being called"
    assert _Tx.cleanup_count == 0


@pytest.mark.asyncio
async def test_dispatch_propagates_tool_exception_and_cleans_up() -> None:
    """Tool body exception propagates; per-call cleanup runs and sees the exception."""

    class _BodyError(RuntimeError):
        pass

    app = a2kit.App("test")
    app.provide(_Tx, per_call=True)

    async def tool(tx: _Tx) -> None:
        raise _BodyError("boom")

    with pytest.raises(_BodyError, match="boom"):
        async with build(app) as app:
            async with app._resolver.call_scope(tool, {}) as kw:
                await tool(**kw)

    assert _Tx.cleanup_count == 1
    assert isinstance(_Tx.last_exc, _BodyError), f"per-call cleanup did not see propagating exception, saw {_Tx.last_exc!r}"


# --- pre_hook plumbing (dispatch-lifecycle-wiring §2) ---------------------


class _ConnCfg:
    def __init__(self, host: str) -> None:
        self.host = host


class _Store:
    def __init__(self, conn: _ConnCfg) -> None:
        self.conn = conn


def _make_store(conn: _ConnCfg) -> _Store:
    return _Store(conn)


@pytest.mark.asyncio
async def test_pre_hook_runs_before_di_resolution() -> None:
    """``pre_hook`` is awaited and its output replaces ``wire_kwargs`` before DI."""
    call_log: list[str] = []

    async def hook(fn: object, wire: dict, seed: Callable[[type, object], None]) -> dict:
        call_log.append("hook")
        # Convert the wire connection string to a typed config.
        return {**wire, "conn": _ConnCfg(wire["conn_str"])}

    async def tool(conn: _ConnCfg, tx: _Tx) -> str:
        call_log.append("tool")
        return conn.host

    app = a2kit.App("hook-order")
    app.provide(_Tx, per_call=True)

    async with build(app) as app, app._resolver.call_scope(tool, {"conn_str": "h1"}, pre_hook=hook) as kw:
        result = await tool(**kw)

    assert call_log == ["hook", "tool"]
    assert result == "h1"
    # _Tx was DI-resolved alongside the hook-supplied conn:
    assert _Tx.instances_created == 1


@pytest.mark.asyncio
async def test_pre_hook_output_seeds_chain_resolution() -> None:
    """A wire-resolved typed config from the hook is visible to the DI chain.

    The tool param is ``store: Store`` where ``Store``'s factory takes
    ``conn: _ConnCfg``. The hook resolves ``conn`` from the wire string;
    the chain finds the wire-resolved instance instead of trying to
    construct one through a (non-existent) provider for ``_ConnCfg``.
    """

    async def hook(fn: object, wire: dict, seed: Callable[[type, object], None]) -> dict:
        conn = _ConnCfg(wire["conn_str"])
        seed(_ConnCfg, conn)  # publish typed instance explicitly on the child
        return {**wire, "conn": conn}

    async def tool(store: _Store) -> str:
        return store.conn.host

    app = a2kit.App("chain-seed")
    # _Store depends on _ConnCfg (seeded by hook per-call), so it must be
    # per_call too — app-scope would violate the scope contract.
    app.provide(_Store, _make_store, per_call=True)

    async with build(app) as app, app._resolver.call_scope(tool, {"conn_str": "h2"}, pre_hook=hook) as kw:
        result = await tool(**kw)

    assert result == "h2"
