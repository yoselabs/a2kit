"""scope_filter + ephemeral wrappers."""

from __future__ import annotations

import asyncio

import pytest

from a2kit.packages.connections import (
    ConnectionNotFound,
    ConnectionStore,
    EphemeralAwareStore,
    FilteredStore,
    scope_filter,
)
from .conftest import TripleConfig, TripleKey, WidgetConfig


def test_scope_filter_none_returns_base(widget_store: ConnectionStore[WidgetConfig]) -> None:
    assert scope_filter(widget_store, None) is widget_store


def test_filtered_store_matches(triple_store: ConnectionStore[TripleConfig]) -> None:
    for k in (TripleKey("a", "dev", "db1"), TripleKey("b", "prod", "db2")):
        asyncio.run(triple_store.save(TripleConfig(key=k, token="t")))
    filt = scope_filter(triple_store, "prod")
    listed = asyncio.run(filt.list_connections())
    assert [c.key for c in listed] == [("b", "prod", "db2")]
    with pytest.raises(ConnectionNotFound):
        asyncio.run(filt.load(("a", "dev", "db1")))
    assert isinstance(filt, FilteredStore)


def test_ephemeral_aware_store(widget_store: ConnectionStore[WidgetConfig]) -> None:
    asyncio.run(widget_store.save(WidgetConfig(key=("base",), token="t")))
    eph = WidgetConfig(key=("ghost",), token="ephemeral")
    proxy = EphemeralAwareStore(widget_store, {("ghost",): eph})
    out = asyncio.run(proxy.load(("ghost",)))
    assert out is eph
    base = asyncio.run(proxy.load(("base",)))
    assert base.key == ("base",)
    listed = asyncio.run(proxy.list_connections())
    keys = sorted(tuple(c.key) for c in listed)
    assert keys == [("base",), ("ghost",)]


def test_ephemeral_aware_store_no_base() -> None:
    eph = WidgetConfig(key=("only",), token="t")
    proxy = EphemeralAwareStore(None, {("only",): eph})
    out = asyncio.run(proxy.load(("only",)))
    assert out is eph
    with pytest.raises(ConnectionNotFound):
        asyncio.run(proxy.load(("missing",)))
