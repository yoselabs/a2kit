from __future__ import annotations

from uncalled_for import Depends

import a2kit


async def real_get_conn(*, connection: str) -> dict:
    return {"connection": connection, "real": True}


async def fake_get_conn(*, connection: str) -> dict:
    return {"connection": connection, "real": False}


class _Probe(a2kit.Router):
    @a2kit.read("get")
    async def get(self, *, conn: dict = Depends(real_get_conn), connection: str = "default") -> dict:
        return {"got": conn}


def test_use_factory_binds_alternative():
    app = a2kit.App("probe").use(_Probe()).use_factory(fake_get_conn, as_=real_get_conn)
    fn = app.tools()[0]
    sig = __import__("inspect").signature(fn)
    conn_default = sig.parameters["conn"].default
    assert getattr(conn_default, "factory", None) is fake_get_conn


def test_use_factory_returns_app_for_chaining():
    app = a2kit.App("probe")
    result = app.use_factory(fake_get_conn, as_=real_get_conn)
    assert result is app


def test_use_factory_overwrite_replaces_previous_binding():
    async def another(*, connection: str) -> dict:
        return {"connection": connection, "real": False, "another": True}

    app = a2kit.App("probe").use(_Probe()).use_factory(fake_get_conn, as_=real_get_conn).use_factory(another, as_=real_get_conn)
    fn = app.tools()[0]
    sig = __import__("inspect").signature(fn)
    assert sig.parameters["conn"].default.factory is another


def test_tools_without_factory_pass_through_unchanged():
    raw_app = a2kit.App("probe").use(_Probe())
    fn = raw_app.tools()[0]
    sig = __import__("inspect").signature(fn)
    assert sig.parameters["conn"].default.factory is real_get_conn


def test_factories_dict_is_a_copy():
    app = a2kit.App("probe").use_factory(fake_get_conn, as_=real_get_conn)
    snapshot = app.factories()
    snapshot[real_get_conn] = lambda: None
    assert app.factories()[real_get_conn] is fake_get_conn
