"""Tests for the fat v0.2 a2kit.tool decorator (connection lookup, write, xml, otel, stream)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, NamedTuple

import pytest

import a2kit
from a2kit import (
    ConnectionInfo,
    ConnectionNotFound,
    ConnectionStore,
    ResolverRegistry,
    ToolCallContamination,
    WriteNotAllowed,
)
from a2kit._context import _RouterContext
from a2kit.tools import (
    _get_current_transport,
    _set_current_transport,
    assert_clean_string,
)


def _ctx(name: str = "test") -> _RouterContext[Any]:
    """Build a fresh per-test router context for `info` access."""
    return _RouterContext(router_name=name, fqn=f"tests.{name}")


class WidgetConn(ConnectionInfo):
    url: str
    api_key: str
    read_only: bool = True


@pytest.fixture
def widget_store(tmp_path: Path) -> ConnectionStore[WidgetConn]:
    store: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    store.save(WidgetConn(key=("prod",), url="https://api", api_key="literal-key"))
    return store


# -- bare decorator (must match v0.1) ----------------------------------------


async def test_bare_decorator_behaves_like_v01() -> None:
    @a2kit.tool()
    async def f(x: int) -> dict:
        return {"x": x}

    assert await f(1) == {"x": 1}


# -- connection lookup -------------------------------------------------------


async def test_connection_lookup_injects_resolved_info(widget_store: ConnectionStore[WidgetConn]) -> None:
    ctx = _ctx()

    @a2kit.tool(store=widget_store, connection_param="connection", router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert await get("prod") == {"url": "https://api"}


async def test_connection_lookup_missing_raises(widget_store: ConnectionStore[WidgetConn]) -> None:
    @a2kit.tool(store=widget_store, connection_param="connection")
    async def get(connection: str) -> dict:
        return {}

    with pytest.raises(ConnectionNotFound):
        await get("nope")


async def test_connection_ephemeral_priority(widget_store: ConnectionStore[WidgetConn]) -> None:
    # v0.8: ephemeral connections live at the Router/store layer, not on the
    # tool decorator. We exercise the same behaviour via _EphemeralAwareStore
    # directly (the proxy Router._apply_bindings builds at runtime).
    from a2kit.scaffold import _EphemeralAwareStore  # noqa: PLC0415

    eph = {("eph",): WidgetConn(key=("eph",), url="https://eph", api_key="x")}
    ctx = _ctx()
    proxy = _EphemeralAwareStore(widget_store, eph)

    @a2kit.tool(store=proxy, connection_param="connection", router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert await get("eph") == {"url": "https://eph"}


async def test_connection_no_store_only_ephemeral() -> None:
    from a2kit.scaffold import _EphemeralAwareStore  # noqa: PLC0415

    eph = {("eph",): WidgetConn(key=("eph",), url="https://eph", api_key="x")}
    ctx = _ctx()
    proxy = _EphemeralAwareStore(None, eph)

    @a2kit.tool(store=proxy, connection_param="connection", router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert await get("eph") == {"url": "https://eph"}


async def test_connection_no_store_missing_raises() -> None:
    @a2kit.tool(connection_param="connection")
    async def get(connection: str) -> dict:
        return {}

    with pytest.raises(ConnectionNotFound):
        await get("missing")


async def test_connection_tuple_key(tmp_path: Path) -> None:
    class TripleKey(NamedTuple):
        project: str
        env: str
        db: str

    class TripleConn(ConnectionInfo, key=TripleKey):
        url: str

    store: ConnectionStore[TripleConn] = ConnectionStore(tmp_path / "c", TripleConn)
    store.save(TripleConn(key=("a", "b", "c"), url="x"))
    ctx: _RouterContext[TripleConn] = _RouterContext(router_name="triple", fqn="tests.triple-tuple")

    @a2kit.tool(store=store, connection_param="conn", router_context=ctx)
    async def get(conn: tuple[str, ...]) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert await get(("a", "b", "c")) == {"url": "x"}


async def test_connection_list_key_coerced(tmp_path: Path) -> None:
    class TripleKey(NamedTuple):
        project: str
        env: str
        db: str

    class TripleConn(ConnectionInfo, key=TripleKey):
        url: str

    store: ConnectionStore[TripleConn] = ConnectionStore(tmp_path / "c", TripleConn)
    store.save(TripleConn(key=("a", "b", "c"), url="x"))
    ctx: _RouterContext[TripleConn] = _RouterContext(router_name="triple", fqn="tests.triple-list")

    @a2kit.tool(store=store, connection_param="conn", router_context=ctx)
    async def get(conn: list[str]) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert await get(["a", "b", "c"]) == {"url": "x"}


async def test_connection_invalid_type_raises(widget_store: ConnectionStore[WidgetConn]) -> None:
    @a2kit.tool(store=widget_store, connection_param="connection")
    async def get(connection: Any) -> dict:
        return {}

    with pytest.raises(TypeError):
        await get(123)


async def test_resolve_info_strings_no_op_path(tmp_path: Path) -> None:
    """A connection with only the (tuple) key — nothing to resolve. Hits the early-return path."""

    class BareConn(ConnectionInfo):
        pass

    store: ConnectionStore[BareConn] = ConnectionStore(tmp_path / "c", BareConn)
    store.save(BareConn(key=("p",)))
    ctx: _RouterContext[BareConn] = _RouterContext(router_name="bare", fqn="tests.bare")

    @a2kit.tool(store=store, connection_param="connection", router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        return {"k": info.key}

    out = await get("p")
    assert out == {"k": ("p",)}


# -- token resolution --------------------------------------------------------


async def test_token_resolution_runs_on_strings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIDGET_KEY", "real-key-from-env")
    store: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    store.save(WidgetConn(key=("p",), url="https://api", api_key="${WIDGET_KEY}"))

    ctx: _RouterContext[WidgetConn] = _RouterContext(router_name="w", fqn="tests.w-tok")
    captured: dict[str, str] = {}

    @a2kit.tool(store=store, connection_param="connection", router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        captured["api_key"] = info.api_key
        return {}

    await get("p")
    assert captured["api_key"] == "real-key-from-env"


async def test_token_resolution_custom_registry(tmp_path: Path) -> None:
    store: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    store.save(WidgetConn(key=("p",), url="https://api", api_key="raw"))
    reg = ResolverRegistry()
    reg.register(lambda v: v == "raw", lambda _v: "swapped")

    ctx: _RouterContext[WidgetConn] = _RouterContext(router_name="w", fqn="tests.w-reg")
    captured: dict[str, str] = {}

    @a2kit.tool(store=store, connection_param="connection", resolver_registry=reg, router_context=ctx)
    async def get(connection: str) -> dict:
        info = ctx.info()
        captured["api_key"] = info.api_key
        return {}

    await get("p")
    assert captured["api_key"] == "swapped"


# -- write enforcement -------------------------------------------------------


async def test_write_blocked_on_read_only(widget_store: ConnectionStore[WidgetConn]) -> None:
    @a2kit.tool(store=widget_store, connection_param="connection", write=True)
    async def update(connection: str) -> dict:
        return {}

    with pytest.raises(WriteNotAllowed):
        await update("prod")


async def test_write_allowed_when_read_write(tmp_path: Path) -> None:
    store: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    store.save(WidgetConn(key=("rw",), url="https://api", api_key="x", read_only=False))

    @a2kit.tool(store=store, connection_param="connection", write=True)
    async def update(connection: str) -> dict:
        return {"ok": True}

    assert await update("rw") == {"ok": True}


# -- tool-call guard ---------------------------------------------------------


async def test_tool_call_guard_raises_on_contamination() -> None:
    @a2kit.tool()
    async def f(text: str) -> dict:
        return {"text": text}

    with pytest.raises(ToolCallContamination):
        await f('<parameter name="x">foo')


async def test_tool_call_guard_disabled() -> None:
    @a2kit.tool(tool_call_guard=False)
    async def f(text: str) -> dict:
        return {"text": text}

    out = await f('<parameter name="x">foo')
    assert out["text"].startswith("<parameter")


def test_assert_clean_string_helper() -> None:
    assert_clean_string("clean", "p")
    with pytest.raises(ToolCallContamination):
        assert_clean_string('<parameter name="x">y', "p")


def test_assert_clean_string_non_str_passes() -> None:
    # type-incorrect call is a no-op (defensive)
    assert_clean_string(123, "p")  # type: ignore[arg-type]


# -- transport seam + streaming ---------------------------------------------


def test_transport_seam_default_stdio() -> None:
    _set_current_transport(None)
    assert _get_current_transport() == "stdio"


async def test_streaming_collects_on_stdio() -> None:
    _set_current_transport("stdio")

    async def gen() -> AsyncIterator[int]:
        for i in range(3):
            yield i

    @a2kit.tool(streaming=True)
    async def stream() -> AsyncIterator[int]:
        return gen()

    result = await stream()
    assert result == [0, 1, 2]


async def test_streaming_passes_through_on_http() -> None:
    _set_current_transport("http")

    async def gen() -> AsyncIterator[int]:
        for i in range(3):
            yield i

    @a2kit.tool(streaming=True)
    async def stream() -> AsyncIterator[int]:
        return gen()

    out = await stream()
    # HTTP transport: the result is still the async iter
    assert hasattr(out, "__aiter__")
    collected = [item async for item in out]
    assert collected == [0, 1, 2]
    _set_current_transport(None)


async def test_streaming_off_returns_value_directly() -> None:
    @a2kit.tool(streaming=False)
    async def f() -> dict:
        return {"a": 1}

    assert await f() == {"a": 1}


# -- otel --------------------------------------------------------------------


async def test_otel_noop_when_no_provider() -> None:
    # Default ProxyTracerProvider → _NullSpan; tool just runs.
    @a2kit.tool(otel=True)
    async def f() -> dict:
        return {"ok": True}

    assert await f() == {"ok": True}


async def test_otel_disabled() -> None:
    @a2kit.tool(otel=False)
    async def f() -> dict:
        return {"ok": True}

    assert await f() == {"ok": True}


async def test_otel_active_provider_sets_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch trace.get_tracer_provider to return a fake non-default provider."""

    class FakeSpan:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    captured = FakeSpan()

    class FakeCM:
        def __enter__(self) -> FakeSpan:
            return captured

        def __exit__(self, *exc: object) -> None:
            return None

    class FakeTracer:
        def start_as_current_span(self, _name: str) -> FakeCM:
            return FakeCM()

    class FakeProvider:
        pass

    from opentelemetry import trace

    monkeypatch.setattr(trace, "get_tracer_provider", lambda: FakeProvider())  # noqa: PLW0108
    monkeypatch.setattr(trace, "get_tracer", lambda _name: FakeTracer())  # noqa: PLW0108

    @a2kit.tool(otel=True, tool_name="my_tool")
    async def f() -> dict:
        return {"ok": True}

    await f()
    assert captured.attrs == {"tool.name": "my_tool", "tool.write": False}


async def test_otel_active_provider_with_connection(monkeypatch: pytest.MonkeyPatch, widget_store: ConnectionStore[WidgetConn]) -> None:
    class FakeSpan:
        def __init__(self) -> None:
            self.attrs: dict[str, Any] = {}

        def set_attribute(self, k: str, v: Any) -> None:
            self.attrs[k] = v

    captured = FakeSpan()

    class FakeCM:
        def __enter__(self) -> FakeSpan:
            return captured

        def __exit__(self, *exc: object) -> None:
            return None

    class FakeTracer:
        def start_as_current_span(self, _name: str) -> FakeCM:
            return FakeCM()

    class FakeProvider:
        pass

    from opentelemetry import trace

    monkeypatch.setattr(trace, "get_tracer_provider", lambda: FakeProvider())  # noqa: PLW0108
    monkeypatch.setattr(trace, "get_tracer", lambda _name: FakeTracer())  # noqa: PLW0108

    @a2kit.tool(store=widget_store, connection_param="connection")
    async def get(connection: str) -> dict:
        return {"ok": True}

    await get("prod")
    assert captured.attrs["tool.connection"] == "prod"


async def test_otel_span_without_set_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the branch where the span object has no `set_attribute` method."""

    class FakeCM:
        def __enter__(self) -> object:
            return object()  # bare object — no set_attribute

        def __exit__(self, *exc: object) -> None:
            return None

    class FakeTracer:
        def start_as_current_span(self, _name: str) -> FakeCM:
            return FakeCM()

    class FakeProvider:
        pass

    from opentelemetry import trace

    monkeypatch.setattr(trace, "get_tracer_provider", lambda: FakeProvider())  # noqa: PLW0108
    monkeypatch.setattr(trace, "get_tracer", lambda _name: FakeTracer())  # noqa: PLW0108

    @a2kit.tool(otel=True)
    async def f() -> dict:
        return {"ok": True}

    assert await f() == {"ok": True}


async def test_otel_import_missing_falls_back_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate opentelemetry not installed."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    @a2kit.tool(otel=True)
    async def f() -> dict:
        return {"ok": True}

    assert await f() == {"ok": True}


# -- sync path with fat features --------------------------------------------


def test_sync_with_connection_lookup(widget_store: ConnectionStore[WidgetConn]) -> None:
    ctx: _RouterContext[WidgetConn] = _RouterContext(router_name="w", fqn="tests.w-sync")

    @a2kit.tool(store=widget_store, connection_param="connection", router_context=ctx)
    def get(connection: str) -> dict:
        info = ctx.info()
        return {"url": info.url}

    assert get("prod") == {"url": "https://api"}


def test_sync_tool_call_guard_raises() -> None:
    @a2kit.tool()
    def f(text: str) -> dict:
        return {}

    with pytest.raises(ToolCallContamination):
        f('<parameter name="x">y')


def test_sync_with_enricher_routes() -> None:
    class _E:
        def enrich(self, exc: Exception, *, tool_name: str | None = None) -> Exception:
            return RuntimeError(f"enriched:{exc}")

    @a2kit.tool(enricher=_E())
    def f(text: str) -> dict:
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="enriched:boom"):
        f("ok")


# Ensure asyncio import isn't unused
_ = asyncio
