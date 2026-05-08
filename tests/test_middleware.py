"""Tests for the v0.13 middleware package + contrib.connections middleware.

Each middleware is exercised in isolation against a no-op `call_next`,
asserting that the chain shape (call → ctx → kwargs → result) is honoured.
Integration with the tool decorator is covered by the existing 700+ tests
across `test_tools_fat.py`, `test_v08.py`, and friends.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from a2kit.contrib.connections import (
    lookup_connection_async,
    resolve_connection_key,
    resolve_info_strings,
    write_enforce_factory,
)
from a2kit.exceptions import WriteNotAllowed
from a2kit.middleware import (
    Middleware,  # noqa: F401 — Protocol re-export smoke check
    ToolContext,
    _build_chain,
    capability_guard,
    compose,
    enrich_errors_factory,
    list_view_apply_factory,
    otel_span_factory,
    tool_call_guard,
)


def _make_ctx(**state: Any) -> ToolContext:
    return ToolContext(
        tool_name="t",
        verb="tool",
        write=False,
        capabilities=frozenset(),
        format_hint=None,
        state=dict(state),
    )


async def _identity(**kw: Any) -> dict[str, Any]:
    return kw


# ── compose / chain shape ──


def test_compose_empty_chain_calls_inner_directly() -> None:
    ctx = _make_ctx()
    handler = compose([], _identity, ctx)
    out = asyncio.run(handler(x=1, y=2))
    assert out == {"x": 1, "y": 2}


def test_compose_single_middleware_runs_around_inner() -> None:
    log: list[str] = []

    async def mw(call_next: Any, _ctx: ToolContext, /, **kw: Any) -> Any:
        log.append("before")
        result = await call_next(**kw)
        log.append("after")
        return result

    ctx = _make_ctx()
    handler = compose([mw], _identity, ctx)
    out = asyncio.run(handler(z=3))
    assert out == {"z": 3}
    assert log == ["before", "after"]


def test_compose_right_to_left_order() -> None:
    log: list[str] = []

    def mk(name: str) -> Any:
        async def mw(call_next: Any, _ctx: ToolContext, /, **kw: Any) -> Any:
            log.append(f"{name}:in")
            result = await call_next(**kw)
            log.append(f"{name}:out")
            return result

        return mw

    chain = [mk("outer"), mk("inner")]
    handler = compose(chain, _identity, _make_ctx())
    asyncio.run(handler())
    assert log == ["outer:in", "inner:in", "inner:out", "outer:out"]


# ── _build_chain tiers ──


def test_build_chain_bare_returns_empty() -> None:
    chain = _build_chain(
        verb="read",
        write=False,
        has_listview=False,
        enricher=None,
        router_middleware=None,
        app_middleware=None,
        otel=False,
        tool_call_guard_on=False,
        bare=True,
    )
    assert chain == []


def test_build_chain_default_includes_tier1() -> None:
    chain = _build_chain(
        verb="read",
        write=False,
        has_listview=False,
        enricher=None,
        router_middleware=None,
        app_middleware=None,
        otel=True,
        tool_call_guard_on=True,
        bare=False,
    )
    # otel + tool_call_guard + capability_guard
    assert len(chain) == 3


def test_build_chain_listview_adds_lv() -> None:
    chain = _build_chain(
        verb="list",
        write=False,
        has_listview=True,
        enricher=None,
        router_middleware=None,
        app_middleware=None,
        otel=False,
        tool_call_guard_on=False,
        bare=False,
    )
    # capability_guard + list_view
    assert len(chain) == 2


def test_build_chain_listview_non_list_verb_still_adds() -> None:
    chain = _build_chain(
        verb="read",
        write=False,
        has_listview=True,
        enricher=None,
        router_middleware=None,
        app_middleware=None,
        otel=False,
        tool_call_guard_on=False,
        bare=False,
    )
    assert len(chain) == 2


def test_build_chain_extra_middleware_appended() -> None:
    async def x(call_next: Any, _c: ToolContext, /, **kw: Any) -> Any:
        return await call_next(**kw)

    chain = _build_chain(
        verb="tool",
        write=False,
        has_listview=False,
        enricher=None,
        router_middleware=[x],
        app_middleware=[x],
        otel=False,
        tool_call_guard_on=False,
        bare=False,
        extra_pre=[x],
        extra_post=[x],
    )
    # capability_guard + extra_pre + router + app + extra_post = 5
    assert len(chain) == 5


# ── individual middleware ──


def test_capability_guard_is_passthrough() -> None:
    ctx = _make_ctx()
    handler = compose([capability_guard], _identity, ctx)
    out = asyncio.run(handler(a=1))
    assert out == {"a": 1}


def test_tool_call_guard_passes_clean_kwargs() -> None:
    def fn(a: int = 0) -> int:
        return a

    sig = inspect.signature(fn)
    ctx = _make_ctx(sig=sig)
    handler = compose([tool_call_guard], _identity, ctx)
    out = asyncio.run(handler(a=1))
    assert out == {"a": 1}


def test_tool_call_guard_no_sig_skips_check() -> None:
    ctx = _make_ctx()  # no sig in state
    handler = compose([tool_call_guard], _identity, ctx)
    out = asyncio.run(handler())
    assert out == {}


def test_otel_span_runs_inner() -> None:
    ctx = _make_ctx(connection_key=None)
    handler = compose([otel_span_factory()], _identity, ctx)
    out = asyncio.run(handler(k=1))
    assert out == {"k": 1}


def test_listview_apply_passthrough_when_no_lv_state() -> None:
    ctx = _make_ctx(lv_settings={}, lv_state={}, streaming=False)
    handler = compose([list_view_apply_factory()], _identity, ctx)
    out = asyncio.run(handler())
    assert out == {}


def test_enrich_errors_wraps_exception() -> None:
    async def boom(**_kw: Any) -> Any:
        msg = "boom"
        raise ValueError(msg)

    def enricher(_exc: Exception, _name: str) -> Exception:
        return RuntimeError("enriched")

    mw = enrich_errors_factory(enricher)
    handler = compose([mw], boom, _make_ctx())
    with pytest.raises(RuntimeError, match="enriched"):
        asyncio.run(handler())


# ── contrib.connections re-exports + write_enforce ──


def test_contrib_helpers_resolve_keys() -> None:
    assert resolve_connection_key("foo") == ("foo",)
    assert resolve_connection_key(("a", "b")) == ("a", "b")
    assert resolve_connection_key(["a", "b"]) == ("a", "b")
    with pytest.raises(TypeError):
        resolve_connection_key(123)


def test_contrib_lookup_connection_async_raises_without_store() -> None:
    from a2kit.exceptions import ConnectionNotFound

    with pytest.raises(ConnectionNotFound):
        asyncio.run(lookup_connection_async(("x",), None))


def test_contrib_resolve_info_strings_no_resolvers() -> None:
    from a2kit.connections import ConnectionInfo

    class C(ConnectionInfo):
        host: str = "example.com"

    info = C(key=("a",))
    out = resolve_info_strings(info, None)
    assert out.host == "example.com"


def test_write_enforce_blocks_when_read_only() -> None:
    class FakeInfo:
        read_only = True

    ctx = ToolContext(
        tool_name="t",
        verb="write",
        write=True,
        capabilities=frozenset(),
        state={"loaded_conn": FakeInfo(), "connection_key": ("a",)},
    )
    mw = write_enforce_factory()
    handler = compose([mw], _identity, ctx)
    with pytest.raises(WriteNotAllowed):
        asyncio.run(handler())


def test_write_enforce_allows_when_writable() -> None:
    class FakeInfo:
        read_only = False

    ctx = ToolContext(
        tool_name="t",
        verb="write",
        write=True,
        capabilities=frozenset(),
        state={"loaded_conn": FakeInfo()},
    )
    mw = write_enforce_factory()
    handler = compose([mw], _identity, ctx)
    out = asyncio.run(handler(x=1))
    assert out == {"x": 1}


def test_write_enforce_skipped_when_not_write() -> None:
    class FakeInfo:
        read_only = True

    ctx = ToolContext(
        tool_name="t",
        verb="read",
        write=False,
        capabilities=frozenset(),
        state={"loaded_conn": FakeInfo()},
    )
    mw = write_enforce_factory()
    handler = compose([mw], _identity, ctx)
    out = asyncio.run(handler())
    assert out == {}


def test_make_factory_returns_tuple() -> None:
    from a2kit.contrib import connections

    class Conn:
        pass

    out = connections.make(Conn)
    assert out == (Conn, None)
