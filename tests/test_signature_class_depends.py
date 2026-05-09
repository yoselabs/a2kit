"""``Depends(<class>)`` resolution — class as the injection key.

Stores declare their conn type via ``a2kit.packages.connections.Store[ConnT]``
(Generic) or ``conn_type = ConnT`` (class attribute). The App needs
``app.use(Connections())`` then ``app.use(ConnT)``.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel
from uncalled_for import Depends

import a2kit
from a2kit.packages.connections import (
    ConnectionConfig,
    ConnectionNotRegistered,
    Connections,
    ConnectionStore,
    Store,
)


# --- Fixtures --- #


class ProbeConn(ConnectionConfig):
    db_path: str = "/tmp/probe.jsonl"


class _Item(BaseModel):
    id: str


class ProbeStore(Store[ProbeConn]):
    def __init__(self, conn: ProbeConn) -> None:
        self.conn = conn

    def items(self) -> list[_Item]:
        return [_Item(id="x")]


class ProbeStoreAttr:
    """Store using class-attribute conn_type instead of Generic."""

    conn_type = ProbeConn

    def __init__(self, conn: ProbeConn) -> None:
        self.conn = conn


def _seed_conn(name: str = "default") -> None:
    """Save a saved connection so resolution finds it at call time."""
    cs = ConnectionStore(ProbeConn)
    asyncio.run(cs.save(ProbeConn(key=(name,), db_path="/tmp/probe.jsonl")))


# --- Tests --- #


def test_depends_conn_class_hides_param_from_signature():
    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(ProbeConn), connection: str = "default") -> dict:
            return {"db": conn.db_path}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    fn = app.tools()[0]
    sig = __import__("inspect").signature(fn)
    # `conn` is hidden — auto-injected at call time.
    assert "conn" not in sig.parameters
    assert "connection" in sig.parameters


def test_depends_conn_class_resolves_at_call_time():
    _seed_conn()

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(ProbeConn), connection: str = "default") -> dict:
            return {"db": conn.db_path}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    fn = app.tools()[0]

    async def go() -> dict:
        return await fn(R(), connection="default")

    out = asyncio.run(go())
    assert out["db"] == "/tmp/probe.jsonl"


def test_depends_store_class_resolves_via_generic():
    _seed_conn()

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, store: ProbeStore = Depends(ProbeStore), connection: str = "default") -> dict:
            return {"item_count": len(store.items())}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    fn = app.tools()[0]
    sig = __import__("inspect").signature(fn)
    assert "store" not in sig.parameters

    async def go() -> dict:
        return await fn(R(), connection="default")

    assert asyncio.run(go()) == {"item_count": 1}


def test_depends_store_class_resolves_via_attribute():
    _seed_conn()

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(
            self,
            *,
            store: ProbeStoreAttr = Depends(ProbeStoreAttr),
            connection: str = "default",
        ) -> dict:
            return {"db": store.conn.db_path}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    fn = app.tools()[0]

    async def go() -> dict:
        return await fn(R(), connection="default")

    assert asyncio.run(go()) == {"db": "/tmp/probe.jsonl"}


def test_depends_conn_class_no_plugin_raises_with_hint():
    """No Connections plugin → generic 'no plugin claims this class' TypeError with hint."""

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(ProbeConn), connection: str = "default") -> dict:
            return {}

    app = a2kit.App("p").use(R())  # NOT connected
    with pytest.raises(TypeError, match=r"app\.use|plugin"):
        app.tools()


def test_depends_conn_class_with_plugin_but_unregistered_raises():
    """Connections plugin registered but `app.use(ProbeConn)` not called → ConnectionNotRegistered."""
    from a2kit.packages.connections import Connections

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(ProbeConn), connection: str = "default") -> dict:
            return {}

    app = a2kit.App("p").use(Connections()).use(R())
    with pytest.raises(ConnectionNotRegistered):
        app.tools()


def test_depends_unrecognized_class_raises_with_hint():
    """Class not claimed by any plugin (not ConnectionConfig, no conn_type marker)
    → generic 'no plugin claims this class' TypeError with hint."""

    class _Bare:  # no conn_type, no Generic, not ConnectionConfig
        def __init__(self, _x: object) -> None: ...

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, x: _Bare = Depends(_Bare), connection: str = "default") -> dict:
            return {}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    with pytest.raises(TypeError, match="not handled by any registered plugin"):
        app.tools()


def test_legacy_stub_factory_path_still_works():
    """Backwards compat: the old `Depends(stub_fn)` + use_factory path still works."""

    async def get_conn(*, connection: str) -> ProbeConn:
        msg = "stub"
        raise RuntimeError(msg)

    from a2kit.packages.connections import get_conn_factory

    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(get_conn), connection: str = "default") -> dict:
            return {}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use_factory(get_conn_factory, as_=get_conn).use(R())
    fn = app.tools()[0]
    sig = __import__("inspect").signature(fn)
    # Legacy form keeps the param visible (Depends rewritten by uncalled_for).
    default = sig.parameters["conn"].default
    assert default.factory is get_conn_factory


def test_class_dep_drops_annotation_from_wrapper():
    class R(a2kit.Router):
        @a2kit.read("get")
        async def get(self, *, conn: ProbeConn = Depends(ProbeConn), connection: str = "default") -> dict:
            return {}

    app = a2kit.App("p").use(Connections()).use(ProbeConn).use(R())
    fn = app.tools()[0]
    # The hidden `conn` annotation must be dropped (else schema dumps include it).
    assert "conn" not in fn.__annotations__
    assert "connection" in fn.__annotations__
