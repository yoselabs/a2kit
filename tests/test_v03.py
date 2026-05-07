"""Tests for v0.3-only additions: server-auto-register, KEY_FIELDS load shapes,
docs registry, Feature class, deprecations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from a2kit.scaffold import Feature, FeatureRegistry, MCPRunner


# ---- KEY_FIELDS load shapes -------------------------------------------------


class WidgetConn(ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")
    base_url: str


class FlatConn(ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str


@pytest.fixture
def store(tmp_path: Path) -> ConnectionStore[WidgetConn]:
    s: ConnectionStore[WidgetConn] = ConnectionStore(tmp_path / "c", WidgetConn)
    s.save(WidgetConn(key=("p", "e", "d"), base_url="https://api"))
    return s


@pytest.fixture
def flat_store(tmp_path: Path) -> ConnectionStore[FlatConn]:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    s.save(FlatConn(key=("prod",), url="https://x"))
    return s


def test_load_kwargs(store: ConnectionStore[WidgetConn]) -> None:
    info = store.load(project="p", env="e", db="d")
    assert info.base_url == "https://api"


def test_load_tuple(store: ConnectionStore[WidgetConn]) -> None:
    info = store.load(("p", "e", "d"))
    assert info.base_url == "https://api"


def test_load_list(store: ConnectionStore[WidgetConn]) -> None:
    info = store.load(["p", "e", "d"])
    assert info.base_url == "https://api"


def test_load_positional(store: ConnectionStore[WidgetConn]) -> None:
    info = store.load("p", "e", "d")
    assert info.base_url == "https://api"


def test_load_bare_string_single_field(flat_store: ConnectionStore[FlatConn]) -> None:
    info = flat_store.load("prod")
    assert info.url == "https://x"


def test_load_kwargs_single_field(flat_store: ConnectionStore[FlatConn]) -> None:
    info = flat_store.load(name="prod")
    assert info.url == "https://x"


def test_load_missing_kwarg_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyFieldMissing):
        store.load(project="p", env="e")


def test_load_unknown_kwarg_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(ValueError, match="Unknown key field"):
        store.load(project="p", env="e", db="d", extra="x")


def test_load_arity_mismatch_tuple(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        store.load(("p", "e"))


def test_load_arity_mismatch_list(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        store.load(["p", "e"])


def test_load_arity_mismatch_positional(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        store.load("p", "e")


def test_load_bare_string_arity_mismatch(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyArityMismatch):
        store.load("p")


def test_load_no_args_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(KeyFieldMissing):
        store.load()


def test_load_mixed_args_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(TypeError, match="mix positional"):
        store.load("p", env="e")


def test_delete_kwargs(store: ConnectionStore[WidgetConn]) -> None:
    store.delete(project="p", env="e", db="d")
    with pytest.raises(a2kit.ConnectionNotFound):
        store.load(("p", "e", "d"))


def test_delete_missing_raises(store: ConnectionStore[WidgetConn]) -> None:
    with pytest.raises(a2kit.ConnectionNotFound):
        store.delete(("a", "b", "c"))


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
    """When `@server.tool()` runs first (innermost) and `@a2kit.tool(server=...)`
    runs after, the auto-register sees the existing entry and skips."""
    server = _FakeServer()

    @a2kit.tool(server=server)
    @server.tool()
    def f() -> dict:
        return {}

    names = [t.name for t in server._tool_manager._tools]
    assert names.count("f") == 1


def test_tool_server_unrelated_existing_tool() -> None:
    """A pre-existing tool with a different name does NOT block registration.

    Covers the branch where `getattr(entry, 'name', None) != name`.
    """
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
    """Server without `_tool_manager` still gets a registration call."""

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

    # Existing doc already mentions filter_expr → no injection.
    assert "REGISTERED TEXT" not in (f.__doc__ or "")
    clear_param_docs()


def test_param_doc_no_registry_skips_injection() -> None:
    clear_param_docs()

    @a2kit.tool()
    def f(filter_expr: str) -> dict:
        return {}

    assert (f.__doc__ or "") == ""


def test_param_doc_with_unrelated_registry_entry() -> None:
    """Registry has a param the tool doesn't take — covers the `not in registry` skip."""
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


# ---- Feature class ----------------------------------------------------------


def test_feature_subclass_register() -> None:
    class MyFeat(Feature):
        name = "issues"
        default = True

        def register_read(self, server: Any, store: Any) -> None:
            server.tools.append("issues.read")

        def register_write(self, server: Any, store: Any) -> None:
            server.tools.append("issues.write")

    reg = FeatureRegistry()
    reg.add(MyFeat())

    class _S:
        tools: list[str] = []  # noqa: RUF012

    s = _S()
    s.tools = []
    reg.apply(s, None, include_writes=True)
    assert s.tools == ["issues.read", "issues.write"]


def test_feature_blank_name_raises() -> None:
    class MyFeat(Feature):
        pass

    with pytest.raises(ValueError, match="non-empty"):
        FeatureRegistry().add(MyFeat())


def test_feature_default_register_methods_no_op() -> None:
    """Base Feature class has no-op register methods (cover them)."""
    f = Feature()
    f.register_read(None, None)
    f.register_write(None, None)


# ---- scaffold deprecations --------------------------------------------------


def test_build_cli_warns_when_connection_class_passed(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    with pytest.warns(DeprecationWarning, match="build_cli"):
        a2kit.scaffold.build_cli(s, connection_class=FlatConn)


def test_build_cli_no_kwarg(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    cli = a2kit.scaffold.build_cli(s)
    assert cli.name == "a2kit"


def test_register_ephemeral_with_store(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)
    out = a2kit.scaffold.register_ephemeral_connections(["--register", "ep", "url=https://x"], store=s)
    assert ("ep",) in out


def test_register_ephemeral_warns_when_class_only(tmp_path: Path) -> None:
    with pytest.warns(DeprecationWarning):
        a2kit.scaffold.register_ephemeral_connections(["--register", "ep", "url=https://x"], FlatConn)


def test_register_ephemeral_requires_one_of() -> None:
    with pytest.raises(TypeError, match="store="):
        a2kit.scaffold.register_ephemeral_connections([])


def test_mcprunner_warns_on_connection_class(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)

    class _S:
        def __init__(self) -> None:
            self.settings = type("S", (), {"host": "h", "port": 1})()

        def run(self, transport: str = "stdio") -> None:
            pass

    with pytest.warns(DeprecationWarning, match="MCPRunner"):
        MCPRunner(_S(), store=s, connection_class=FlatConn)


def test_mcprunner_derives_class_from_store(tmp_path: Path) -> None:
    s: ConnectionStore[FlatConn] = ConnectionStore(tmp_path / "c", FlatConn)

    class _S:
        def __init__(self) -> None:
            self.settings = type("S", (), {"host": "h", "port": 1})()

        def run(self, transport: str = "stdio") -> None:
            pass

    runner = MCPRunner(_S(), store=s)
    assert runner.connection_class is FlatConn
