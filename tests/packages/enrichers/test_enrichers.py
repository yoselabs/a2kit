"""Tests for `a2kit.packages.enrichers`."""

from __future__ import annotations

import pytest

from a2kit.packages.enrichers import EnricherFn, chain, connection_enricher, wrap
from a2kit.packages.connections.exceptions import ConnectionNotFound


# ---------- chain ----------


def test_chain_empty_is_identity() -> None:
    enricher = chain()
    exc = ValueError("x")
    assert enricher(exc, "tool") is exc


def test_chain_first_transform_wins() -> None:
    def e1(exc: Exception, _name: str) -> Exception:
        return RuntimeError("e1")

    def e2(exc: Exception, _name: str) -> Exception:  # pragma: no cover
        raise AssertionError("e2 must not run after e1 transforms")

    out = chain(e1, e2)(ValueError("orig"), "t")
    assert isinstance(out, RuntimeError)
    assert str(out) == "e1"


def test_chain_skips_passthrough() -> None:
    def passthrough(exc: Exception, _name: str) -> Exception:
        return exc

    def transform(_exc: Exception, _name: str) -> Exception:
        return RuntimeError("transformed")

    out = chain(passthrough, transform)(ValueError("orig"), "t")
    assert isinstance(out, RuntimeError)
    assert str(out) == "transformed"


# ---------- wrap: identity ----------


def test_wrap_none_returns_fn_identity() -> None:
    def fn(x: int) -> int:
        return x + 1

    assert wrap(fn, None) is fn


# ---------- wrap: sync ----------


def test_wrap_sync_passes_return_value() -> None:
    def fn(x: int) -> int:
        return x * 2

    enricher: EnricherFn = lambda exc, _name: exc  # noqa: E731
    wrapped = wrap(fn, enricher)
    assert wrapped(3) == 6


def test_wrap_sync_calls_enricher_only_on_exception() -> None:
    calls: list[tuple[Exception, str]] = []

    def enricher(exc: Exception, name: str) -> Exception:
        calls.append((exc, name))
        return RuntimeError(f"enriched: {exc}")

    def good() -> str:
        return "ok"

    def bad() -> str:
        raise ValueError("boom")

    assert wrap(good, enricher)() == "ok"
    assert calls == []

    with pytest.raises(RuntimeError, match="enriched: boom"):
        wrap(bad, enricher)()
    assert len(calls) == 1
    assert calls[0][1] == "bad"  # tool_name = fn.__name__


# ---------- wrap: async ----------


@pytest.mark.anyio
async def test_wrap_async_passes_return_value() -> None:
    async def fn(x: int) -> int:
        return x * 3

    enricher: EnricherFn = lambda exc, _name: exc  # noqa: E731
    wrapped = wrap(fn, enricher)
    assert await wrapped(4) == 12


@pytest.mark.anyio
async def test_wrap_async_enriches_exceptions() -> None:
    async def boom() -> None:
        raise ValueError("async boom")

    def enricher(exc: Exception, name: str) -> Exception:
        return RuntimeError(f"{name}: {exc}")

    with pytest.raises(RuntimeError, match="boom: async boom"):
        await wrap(boom, enricher)()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------- connection_enricher ----------


class _FakeStore:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def list(self) -> list[str]:
        return list(self._keys)


def test_connection_enricher_passthrough_on_other_exceptions() -> None:
    store = _FakeStore(["a", "b"])
    enricher = connection_enricher(store)
    exc = ValueError("not a ConnectionNotFound")
    assert enricher(exc, "tool") is exc


def test_connection_enricher_adds_available_and_suggestion() -> None:
    store = _FakeStore(["protea", "datalab", "stripe"])
    enricher = connection_enricher(store)
    exc = ConnectionNotFound(("proteaa",))
    out = enricher(exc, "query")
    assert isinstance(out, ConnectionNotFound)
    msg = str(out)
    assert "proteaa" in msg
    assert "protea" in msg  # close match suggestion
    assert "query" in msg
    assert out.available_connections == ["protea", "datalab", "stripe"]


def test_connection_enricher_no_configured_connections() -> None:
    store = _FakeStore([])
    enricher = connection_enricher(store)
    exc = ConnectionNotFound(("foo",))
    out = enricher(exc, "tool")
    assert isinstance(out, ConnectionNotFound)
    assert "no connections are configured" in str(out)
    assert out.available_connections == []


def test_connection_enricher_store_without_list_method() -> None:
    enricher = connection_enricher(object())
    exc = ConnectionNotFound(("foo",))
    out = enricher(exc, "tool")
    assert isinstance(out, ConnectionNotFound)
    assert out.available_connections == []
