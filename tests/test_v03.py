"""Tests for v0.3 surface that survives into v0.5: server-auto-register,
NamedTuple-key load shapes, docs registry. (Feature/Deprecation tests removed in v0.4.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

import pytest

import a2kit
from a2kit import (
    ConnectionInfo,
    ConnectionStore,
    KeyArityMismatch,
    KeyFieldMissing,
)
from a2kit.docs import (
    clear_param_docs,
    param_doc,
    register_param_doc,
)


class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str


class WidgetConn(ConnectionInfo, key=WidgetKey):
    base_url: str


class FlatConn(ConnectionInfo):
    url: str


@pytest.fixture
async def store(tmp_path: Path) -> ConnectionStore[WidgetConn]:
    s: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    await s.save(WidgetConn(key=("p", "e", "d"), base_url="https://api"))
    return s


@pytest.fixture
async def flat_store(tmp_path: Path) -> ConnectionStore[FlatConn]:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    await s.save(FlatConn(key=("prod",), url="https://x"))
    return s


async def test_load_kwargs(store: ConnectionStore[WidgetConn]) -> None:
    info = await store.load(project="p", env="e", db="d")
    assert info.base_url == "https://api"


async def test_load_tuple(store: ConnectionStore[WidgetConn]) -> None:
    info = await store.load(("p", "e", "d"))
    assert info.base_url == "https://api"


async def test_load_list(store: ConnectionStore[WidgetConn]) -> None:
    info = await store.load(["p", "e", "d"])
    assert info.base_url == "https://api"


async def test_load_positional(store: ConnectionStore[WidgetConn]) -> None:
    info = await store.load("p", "e", "d")
    assert info.base_url == "https://api"


async def test_load_bare_string_single_field(flat_store: ConnectionStore[FlatConn]) -> None:
    info = await flat_store.load("prod")
    assert info.url == "https://x"


async def test_load_kwargs_single_field(flat_store: ConnectionStore[FlatConn]) -> None:
    info = await flat_store.load(name="prod")
    assert info.url == "https://x"


async def test_load_missing_kwarg_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyFieldMissing):
        await store.load(project="p", env="e")


async def test_load_unknown_kwarg_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(ValueError, match="Unknown key field"):
        await store.load(project="p", env="e", db="d", extra="x")


async def test_load_arity_mismatch_tuple(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        await store.load(("p", "e"))


async def test_load_arity_mismatch_list(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        await store.load(["p", "e"])


async def test_load_arity_mismatch_positional(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        await store.load("p", "e")


async def test_load_bare_string_arity_mismatch(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        await store.load("p")


async def test_load_no_args_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyFieldMissing):
        await store.load()


async def test_load_mixed_args_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(TypeError, match="mix positional"):
        await store.load("p", env="e")


async def test_delete_kwargs(store: ConnectionStore[WidgetConn]) -> None:
    await store.delete(project="p", env="e", db="d")
    with pytest.raises(a2kit.ConnectionNotFound):
        await store.load(("p", "e", "d"))


async def test_delete_missing_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(a2kit.ConnectionNotFound):
        await store.delete(("a", "b", "c"))


def test_store_exposes_connection_class(store: ConnectionStore[WidgetConn]) -> None:
    assert store.connection_class is WidgetConn


# ---- Tool decorator: server kwarg auto-registration ------------------------


class _FakeManager:
    def __init__(self) -> None:
        self._tools: list[Any] = []

    def list_tools(self) -> list[Any]:
        return list(self._tools)


class _FakeServer:
    def __init__(self) -> None:
        self._tool_manager = _FakeManager()

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            class _T:
                pass

            t = _T()
            t.name = fn.__name__
            t.fn = fn
            self._tool_manager._tools.append(t)
            return fn

        return deco


def test_tool_server_auto_register() -> None:
    server = _FakeServer()

    @a2kit.tool(server=server)
    def f() -> dict:
        return {}

    names = [t.name for t in server._tool_manager._tools]
    assert names == ["f"]


def test_tool_server_idempotent_when_stacked() -> None:
    server = _FakeServer()

    @a2kit.tool(server=server)
    @server.tool()
    def f() -> dict:
        return {}

    names = [t.name for t in server._tool_manager._tools]
    assert names.count("f") == 1


def test_tool_server_unrelated_existing_tool() -> None:
    server = _FakeServer()

    @server.tool()
    def existing() -> dict:
        return {}

    @a2kit.tool(server=server)
    def new_one() -> dict:
        return {}

    names = [t.name for t in server._tool_manager._tools]
    assert names == ["existing", "new_one"]


def test_tool_server_handles_missing_tool_manager() -> None:
    class _Bare:
        registered: list[str] = []  # noqa: RUF012

        def tool(self, *_a: Any, **_kw: Any) -> Any:
            def deco(fn: Any) -> Any:
                self.registered.append(fn.__name__)
                return fn

            return deco

    server = _Bare()

    @a2kit.tool(server=server)
    def g() -> dict:
        return {}

    assert "g" in server.registered


# ---- docs registry ----------------------------------------------------------


def test_register_and_retrieve_param_doc() -> None:
    clear_param_docs()
    register_param_doc("filter_expr", "JMESPath expression to filter rows.")
    assert "JMESPath" in param_doc("filter_expr")
    clear_param_docs()
    assert param_doc("filter_expr") == ""


def test_param_doc_injection_into_tool_docstring() -> None:
    clear_param_docs()
    register_param_doc("filter_expr", "JMESPath expression to filter rows in output.")

    @a2kit.tool()
    def f(filter_expr: str) -> dict:
        """Pre-existing doc."""
        return {}

    assert "JMESPath" in (f.__doc__ or "")
    clear_param_docs()


def test_param_doc_does_not_override_explicit() -> None:
    clear_param_docs()
    register_param_doc("filter_expr", "REGISTERED TEXT WITH JMESPath.")

    @a2kit.tool()
    def f(filter_expr: str) -> dict:
        """We mention filter_expr inline so registry should skip it."""
        return {}

    assert "REGISTERED TEXT" not in (f.__doc__ or "")
    clear_param_docs()


def test_param_doc_no_registry_skips_injection() -> None:
    clear_param_docs()

    @a2kit.tool()
    def f(filter_expr: str) -> dict:
        return {}

    assert (f.__doc__ or "") == ""


def test_param_doc_with_unrelated_registry_entry() -> None:
    clear_param_docs()
    register_param_doc("never_used", "Doc for a name no tool uses.")

    @a2kit.tool()
    def f(x: int) -> dict:
        return {}

    assert "never_used" not in (f.__doc__ or "")
    clear_param_docs()


def test_param_doc_creates_doc_when_absent() -> None:
    clear_param_docs()
    register_param_doc("widget_id", "Stable opaque identifier for the widget.")

    @a2kit.tool()
    def f(widget_id: str) -> dict:
        return {}

    assert "widget_id" in (f.__doc__ or "")
    clear_param_docs()


# ---- Router class -----------------------------------------------------------


def test_router_subclass_register() -> None:
    from a2kit import Router, RouterRegistry

    class MyRouter(Router):
        def register_read(self, server: Any, store: Any) -> None:
            server.tools.append("issues.read")

        def register_write(self, server: Any, store: Any) -> None:
            server.tools.append("issues.write")

    reg = RouterRegistry()
    reg.add(MyRouter(name="issues", default=True))

    class _S:
        tools: list[str] = []  # noqa: RUF012

    s = _S()
    s.tools = []
    reg.apply(s, None, include_writes=True)
    assert s.tools == ["issues.read", "issues.write"]


def test_router_blank_name_raises() -> None:
    from a2kit import Router

    with pytest.raises(Exception):  # noqa: B017, PT011
        Router(name="")


def test_router_default_register_methods_no_op() -> None:
    from a2kit import Router

    r = Router(name="x")
    r.register_read(None, None)
    r.register_write(None, None)


def test_register_ephemeral_with_store(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    out = a2kit.scaffold.register_ephemeral_connections(["--register", "ep", "url=https://x"], store=s)
    assert ("ep",) in out


def test_mcprunner_derives_class_from_store(tmp_path: Path) -> None:
    from a2kit.scaffold import MCPRunner

    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)

    class _S:
        def __init__(self) -> None:
            self.settings = type("S", (), {"host": "h", "port": 1})()

        def tool(self, *_a: Any, **_kw: Any) -> Any:
            return lambda fn: fn

        def run(self, transport: str = "stdio") -> None:
            pass

    runner = MCPRunner(_S(), store=s)
    assert runner.connection_class is FlatConn
