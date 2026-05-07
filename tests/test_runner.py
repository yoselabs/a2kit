"""Tests for MCPRunner + FeatureRegistry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from a2kit import ConnectionInfo, ConnectionStore
from a2kit.scaffold import FeatureRegistry, MCPRunner


class _FakeServerSettings:
    def __init__(self) -> None:
        self.host = "127.0.0.1"
        self.port = 8000


class _FakeServer:
    def __init__(self) -> None:
        self.settings = _FakeServerSettings()
        self.tools: list[str] = []
        self.run_calls: list[str] = []

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools.append(fn.__name__)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:
        self.run_calls.append(transport)


class WConn(ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str


@pytest.fixture
def store(tmp_path: Path) -> ConnectionStore[WConn]:
    return ConnectionStore(tmp_path / "c", WConn)


# ---- FeatureRegistry --------------------------------------------------------


def test_feature_registry_defaults_and_apply() -> None:
    reg = FeatureRegistry()
    server = _FakeServer()

    @reg.feature("issues", default=True)
    class Issues:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("issues.read")

        @staticmethod
        def register_write(s: Any, _store: Any) -> None:
            s.tools.append("issues.write")

    @reg.feature("sprints")
    class Sprints:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("sprints.read")

    assert reg.feature_names() == ["issues", "sprints"]
    assert reg.defaults() == {"issues"}

    applied = reg.apply(server, None)
    assert applied == ["issues"]
    assert server.tools == ["issues.read"]


def test_feature_registry_explicit_enable_includes_writes() -> None:
    reg = FeatureRegistry()
    server = _FakeServer()

    @reg.feature("a")
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a.read")

        @staticmethod
        def register_write(s: Any, _store: Any) -> None:
            s.tools.append("a.write")

    reg.apply(server, None, enabled=["a"], include_writes=True)
    assert server.tools == ["a.read", "a.write"]


def test_feature_registry_unknown_raises() -> None:
    reg = FeatureRegistry()
    with pytest.raises(ValueError, match="Unknown feature"):
        reg.apply(_FakeServer(), None, enabled=["does-not-exist"])


def test_feature_no_register_methods_skipped() -> None:
    reg = FeatureRegistry()

    @reg.feature("empty", default=True)
    class _Empty:
        pass

    server = _FakeServer()
    reg.apply(server, None)  # should not raise
    assert server.tools == []


# ---- MCPRunner --------------------------------------------------------------


def test_runner_stdio_default() -> None:
    server = _FakeServer()
    runner = MCPRunner(server)
    parsed = runner.run(argv=[])
    assert server.run_calls == ["stdio"]
    assert parsed["http"] is None


def test_runner_explicit_transport_stdio() -> None:
    server = _FakeServer()
    MCPRunner(server).run(argv=[], transport="stdio")
    assert server.run_calls == ["stdio"]


def test_runner_http_default_host_port() -> None:
    server = _FakeServer()
    MCPRunner(server).run(argv=["--http"])
    assert server.run_calls == ["streamable-http"]
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8080


def test_runner_http_with_host_port() -> None:
    server = _FakeServer()
    MCPRunner(server).run(argv=["--http", "0.0.0.0:9000"])  # noqa: S104
    assert server.settings.host == "0.0.0.0"  # noqa: S104
    assert server.settings.port == 9000


def test_runner_http_port_only() -> None:
    server = _FakeServer()
    MCPRunner(server).run(argv=["--http", ":7000"])
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 7000


def test_runner_http_host_only() -> None:
    server = _FakeServer()
    MCPRunner(server).run(argv=["--http", "myhost"])
    assert server.settings.host == "myhost"
    assert server.settings.port == 8080


def test_runner_scope_parsed() -> None:
    parsed = MCPRunner(_FakeServer()).run(argv=["--scope", "prod"])
    assert parsed["scope"] == "prod"


def test_runner_writes_flag() -> None:
    parsed = MCPRunner(_FakeServer()).run(argv=["--writes"])
    assert parsed["writes"] is True


def test_runner_enable_comma_separated() -> None:
    parsed = MCPRunner(_FakeServer()).run(argv=["--enable", "a,b"])
    assert parsed["enable"] == ["a", "b"]


def test_runner_no_enable_excludes_default() -> None:
    reg = FeatureRegistry()
    server = _FakeServer()

    @reg.feature("a", default=True)
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a")

    @reg.feature("b", default=True)
    class B:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("b")

    MCPRunner(server, feature_registry=reg).run(argv=["--no-enable", "b"])
    assert server.tools == ["a"]


def test_runner_register_ephemeral(store: ConnectionStore[WConn]) -> None:
    server = _FakeServer()
    parsed = MCPRunner(server, store=store, connection_class=WConn).run(argv=["--register", "ep", "url=https://x"])
    assert ("ep",) in parsed["ephemeral"]
    assert parsed["ephemeral"][("ep",)].url == "https://x"


def test_runner_no_connection_class_skips_ephemeral() -> None:
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--register", "ep", "url=x"])
    assert parsed["ephemeral"] == {}


def test_runner_features_applied(store: ConnectionStore[WConn]) -> None:
    reg = FeatureRegistry()
    server = _FakeServer()

    @reg.feature("a")
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a.read")

    MCPRunner(server, store=store, feature_registry=reg).run(argv=["--enable", "a"])
    assert server.tools == ["a.read"]


def test_runner_unknown_flag_skipped() -> None:
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--made-up", "x", "--scope", "k"])
    assert parsed["scope"] == "k"


def test_runner_register_terminated_by_other_flag(store: ConnectionStore[WConn]) -> None:
    server = _FakeServer()
    parsed = MCPRunner(server, store=store, connection_class=WConn).run(argv=["--register", "ep", "url=https://x", "--scope", "ep"])
    assert parsed["scope"] == "ep"
    assert ("ep",) in parsed["ephemeral"]


def test_runner_uses_sys_argv_when_argv_none(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _FakeServer()
    monkeypatch.setattr("sys.argv", ["prog", "--scope", "x"])
    parsed = MCPRunner(server).run()
    assert parsed["scope"] == "x"


def test_runner_transport_seam_clears_after_run() -> None:
    from a2kit.tools import _get_current_transport

    server = _FakeServer()
    MCPRunner(server).run(argv=[])
    # post-run, the seam is cleared back to None (default fallback = stdio)
    assert _get_current_transport() == "stdio"


def test_runner_transport_seam_on_run_failure() -> None:
    from a2kit.tools import _get_current_transport

    class _Boom(_FakeServer):
        def run(self, transport: str = "stdio") -> None:
            raise RuntimeError("crash")

    with pytest.raises(RuntimeError, match="crash"):
        MCPRunner(_Boom()).run(argv=[])
    assert _get_current_transport() == "stdio"
