"""Container — typed providers, parameter-annotation chaining, per-call cache."""

from __future__ import annotations

import asyncio

import pytest

from a2kit.packages.connections.container import Container, UnresolvableType


class _Cfg:
    def __init__(self, connection: str) -> None:
        self.connection = connection


class _Store:
    def __init__(self, cfg: _Cfg) -> None:
        self.cfg = cfg


def test_register_then_resolve_simple_chain() -> None:
    c = Container()
    c.register(_Cfg, _Cfg)
    c.register(_Store, _Store)

    async def _go() -> None:
        store = await c.resolve(_Store, connection="foo")
        assert isinstance(store, _Store)
        assert isinstance(store.cfg, _Cfg)
        assert store.cfg.connection == "foo"

    asyncio.run(_go())


def test_class_as_factory_when_factory_omitted() -> None:
    c = Container()
    c.register(_Cfg)
    c.register(_Store)

    async def _go() -> None:
        store = await c.resolve(_Store, connection="bar")
        assert store.cfg.connection == "bar"

    asyncio.run(_go())


def test_per_call_cache_dedupes_within_one_resolution() -> None:
    seen: list[_Cfg] = []

    def cfg_factory(connection: str) -> _Cfg:
        cfg = _Cfg(connection)
        seen.append(cfg)
        return cfg

    class _Audit:
        def __init__(self, cfg: _Cfg, store: _Store) -> None:
            self.cfg = cfg
            self.store = store

    c = Container()
    c.register(_Cfg, cfg_factory)
    c.register(_Store)
    c.register(_Audit)

    async def _go() -> None:
        cache: dict = {}
        audit = await c.resolve(_Audit, connection="x", cache=cache)
        # Both the direct cfg and the store.cfg are the same instance.
        assert audit.cfg is audit.store.cfg
        assert len(seen) == 1

    asyncio.run(_go())


def test_unresolvable_raises_with_chain() -> None:
    c = Container()
    c.register(_Store)  # but no _Cfg provider

    async def _go() -> None:
        with pytest.raises(UnresolvableType) as ei:
            await c.resolve(_Store, connection="x")
        assert ei.value.type_ is _Cfg

    asyncio.run(_go())


def test_async_factory_resolution() -> None:
    async def afactory(connection: str) -> _Cfg:
        return _Cfg(connection)

    c = Container()
    c.register(_Cfg, afactory)
    c.register(_Store)

    async def _go() -> None:
        s = await c.resolve(_Store, connection="zz")
        assert s.cfg.connection == "zz"

    asyncio.run(_go())


def test_partition_kwargs_distinguishes_wire_from_injectable() -> None:
    c = Container()
    c.register(_Cfg)
    c.register(_Store)

    def fn(*, store: _Store, task_id: str, limit: int = 10) -> None:  # noqa: ARG001
        return None

    wire, inject, needs_conn = c.partition_kwargs(fn)
    assert wire == {"task_id", "limit"}
    assert inject == {"store"}
    assert needs_conn is True


def test_partition_no_injectables_no_connection() -> None:
    c = Container()  # empty registry

    def fn(*, x: int) -> None:  # noqa: ARG001
        return None

    wire, inject, needs_conn = c.partition_kwargs(fn)
    assert wire == {"x"}
    assert inject == set()
    assert needs_conn is False


def test_apply_kwargs_resolves_injectables() -> None:
    c = Container()
    c.register(_Cfg)
    c.register(_Store)

    def fn(*, store: _Store, n: int) -> dict:  # noqa: ARG001
        return {}

    async def _go() -> None:
        out = await c.apply_kwargs(fn, {"connection": "abc", "n": 5})
        assert isinstance(out["store"], _Store)
        assert out["n"] == 5
        # connection is wire-only when fn doesn't declare it
        assert "connection" not in out

    asyncio.run(_go())


def test_replace_provider_last_write_wins() -> None:
    c = Container()
    c.register(_Cfg, lambda connection: _Cfg(f"first-{connection}"))
    c.register(_Cfg, lambda connection: _Cfg(f"second-{connection}"))
    c.register(_Store)

    async def _go() -> None:
        s = await c.resolve(_Store, connection="x")
        assert s.cfg.connection == "second-x"

    asyncio.run(_go())
