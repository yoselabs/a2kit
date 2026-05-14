"""BDD: ``Container.dispatch`` per-call dispatch helper.

Covers spec ``di-per-call-scope`` §4.4-§4.5: the framework's per-tool
dispatch path opens a child resolver, resolves kwargs (Lazy[T] + eager),
runs the tool body inside the child's lifetime, and unwinds per-call
cleanup with exception preservation.
"""

from __future__ import annotations

import pytest

import a2kit
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
    """``dispatch(fn, wire)`` yields merged resolved + wire kwargs."""
    app = a2kit.App("test")
    app.provide(_Tx, per_call=True)

    async def tool(tx: _Tx, name: str) -> str:
        return f"{name}:{type(tx).__name__}"

    async with app, app._resolver.dispatch(tool, {"name": "alice"}) as kw:
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

    async with app, app._resolver.dispatch(tool, {"flag": False}) as kw:
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
        async with app:
            async with app._resolver.dispatch(tool, {}) as kw:
                await tool(**kw)

    assert _Tx.cleanup_count == 1
    assert isinstance(_Tx.last_exc, _BodyError), (
        f"per-call cleanup did not see propagating exception, saw {_Tx.last_exc!r}"
    )
