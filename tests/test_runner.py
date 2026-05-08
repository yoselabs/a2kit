"""Tests for MCPRunner + RouterRegistry — v0.4 (post-deprecation removal)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from a2kit import ConnectionConfig, ConnectionStore, Router
from a2kit.scaffold import MCPRunner, RouterRegistry


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


class WConn(ConnectionConfig):
    url: str


@pytest.fixture
def store(tmp_path: Path) -> ConnectionStore[WConn]:
    return ConnectionStore(tmp_path / "c", WConn)


# ---- RouterRegistry ---------------------------------------------------------


def test_router_registry_defaults_and_apply() -> None:
    reg = RouterRegistry()
    server = _FakeServer()

    @reg.router("issues", default=True)
    class Issues:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("issues.read")

        @staticmethod
        def register_write(s: Any, _store: Any) -> None:
            s.tools.append("issues.write")

    @reg.router("sprints", default=False)
    class Sprints:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("sprints.read")

    assert reg.names() == ["issues", "sprints"]
    assert reg.defaults() == {"issues"}

    applied = reg.apply(server, None)
    assert applied == ["issues"]
    assert server.tools == ["issues.read"]


def test_router_registry_explicit_enable_includes_writes() -> None:
    reg = RouterRegistry()
    server = _FakeServer()

    @reg.router("a")
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a.read")

        @staticmethod
        def register_write(s: Any, _store: Any) -> None:
            s.tools.append("a.write")

    reg.apply(server, None, enabled=["a"], include_writes=True)
    assert server.tools == ["a.read", "a.write"]


def test_router_registry_unknown_raises() -> None:
    reg = RouterRegistry()
    with pytest.raises(ValueError, match="Unknown router"):
        reg.apply(_FakeServer(), None, enabled=["does-not-exist"])


def test_router_no_register_methods_skipped() -> None:
    reg = RouterRegistry()

    @reg.router("empty", default=True)
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


def test_runner_select_string() -> None:
    parsed = MCPRunner(_FakeServer()).run(argv=["--select", "default and not write"])
    assert parsed["select"] == "default and not write"


def test_runner_no_enable_excludes_default_via_select() -> None:
    """v0.4: `--no-enable b` is gone; use --select to exclude routers."""
    reg = RouterRegistry()
    server = _FakeServer()

    @reg.router("a", default=True)
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a")

    @reg.router("b", default=True)
    class B:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("b")

    MCPRunner(server, router_registry=reg).run(argv=["--select", "default and not router:b"])
    assert server.tools == ["a"]


def test_runner_register_ephemeral(store: ConnectionStore[WConn]) -> None:
    server = _FakeServer()
    parsed = MCPRunner(server, connection_store=store).run(argv=["--register", "ep", "url=https://x"])
    assert ("ep",) in parsed["ephemeral"]
    assert parsed["ephemeral"][("ep",)].url == "https://x"


def test_runner_no_store_skips_ephemeral() -> None:
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--register", "ep", "url=x"])
    assert parsed["ephemeral"] == {}


def test_runner_routers_applied(store: ConnectionStore[WConn]) -> None:
    reg = RouterRegistry()
    server = _FakeServer()

    @reg.router("a")
    class A:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("a.read")

    MCPRunner(server, connection_store=store, router_registry=reg).run(argv=["--select", "router:a"])
    assert server.tools == ["a.read"]


def test_runner_unknown_flag_skipped() -> None:
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--made-up", "x", "--scope", "k"])
    assert parsed["scope"] == "k"


def test_runner_register_terminated_by_other_flag(store: ConnectionStore[WConn]) -> None:
    server = _FakeServer()
    parsed = MCPRunner(server, connection_store=store).run(argv=["--register", "ep", "url=https://x", "--scope", "ep"])
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
    assert _get_current_transport() == "stdio"


def test_runner_transport_seam_on_run_failure() -> None:
    from a2kit.tools import _get_current_transport

    class _Boom(_FakeServer):
        def run(self, transport: str = "stdio") -> None:
            raise RuntimeError("crash")

    with pytest.raises(RuntimeError, match="crash"):
        MCPRunner(_Boom()).run(argv=[])
    assert _get_current_transport() == "stdio"


# ---- v0.4 default_select auto-load + clean-cut removals ---------------------


def test_runner_default_select_kwarg_str() -> None:
    runner = MCPRunner(_FakeServer(), default_select="default")
    assert runner.default_select.op == "atom"


def test_runner_default_select_kwarg_expr() -> None:
    from a2kit import sel

    runner = MCPRunner(_FakeServer(), default_select=sel("default"))
    assert runner.default_select.op == "atom"


def test_runner_includes_writes_when_select_mentions_write() -> None:
    server = _FakeServer()
    reg = RouterRegistry()
    visited: list[str] = []

    class A(Router):
        def register_read(self, s: Any, _: Any) -> None:
            visited.append("read")

        def register_write(self, s: Any, _: Any) -> None:
            visited.append("write")

    reg.add(A(name="a", default=True))
    MCPRunner(server, router_registry=reg).run(argv=["--select", "a and write"])
    assert "write" in visited


def test_runner_invalid_atom_tolerated() -> None:
    server = _FakeServer()
    reg = RouterRegistry()
    reg.add(Router(name="a", default=True))
    MCPRunner(server, router_registry=reg).run(argv=["--select", "a or bogus_atom"])


def test_runner_explicit_positive_no_match_falls_back() -> None:
    server = _FakeServer()
    reg = RouterRegistry()
    reg.add(Router(name="a", default=True))
    MCPRunner(server, router_registry=reg).run(argv=["--select", "router:nonexistent"])


def test_runner_default_select_pyproject_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When no kwarg is passed, MCPRunner reads default_select from the nearest pyproject.toml."""
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[tool.a2kit.runner]\ndefault_select = "default and not destructive"\n')
    monkeypatch.chdir(proj)
    runner = MCPRunner(_FakeServer())
    assert runner.default_select.op == "and"


def test_runner_default_select_pyproject_invalid_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[tool.a2kit.runner]\ndefault_select = "bad +++ syntax"\n')
    monkeypatch.chdir(proj)
    with pytest.warns(UserWarning, match="failed to parse"):
        runner = MCPRunner(_FakeServer())
    # Hard default kicks in
    assert runner.default_select.op == "and"


def test_runner_pyproject_capabilities_registered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[tool.a2kit.capabilities]\n"my-feature" = { description = "Test cap" }\n')
    monkeypatch.chdir(proj)
    MCPRunner(_FakeServer())
    from a2kit import capabilities

    assert capabilities.get("my-feature") is not None


def test_runner_pyproject_capabilities_bad_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "myproj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text('[tool.a2kit.capabilities]\nbroken = "not-a-table"\n')
    monkeypatch.chdir(proj)
    with pytest.raises(ValueError, match="must be a table"):
        MCPRunner(_FakeServer())


def test_feature_alias_removed() -> None:
    import a2kit

    with pytest.raises(ImportError, match="Router"):
        _ = a2kit.Feature  # type: ignore[attr-defined]


def test_feature_registry_alias_removed() -> None:
    import a2kit

    with pytest.raises(ImportError, match="RouterRegistry"):
        _ = a2kit.FeatureRegistry  # type: ignore[attr-defined]


def test_a2kit_unknown_attr_passthrough() -> None:
    import a2kit

    with pytest.raises(AttributeError):
        _ = a2kit.does_not_exist  # type: ignore[attr-defined]


def test_register_ephemeral_requires_store() -> None:
    """v0.4: positional connection_class is gone; only store= works."""
    from a2kit.scaffold import register_ephemeral_connections

    with pytest.raises(TypeError):
        register_ephemeral_connections([], "not-a-store")  # type: ignore[arg-type]


def test_build_cli_no_kwarg_works(tmp_path: Path) -> None:
    """v0.4: build_cli no longer accepts connection_class= kwarg."""
    from a2kit.scaffold import build_cli

    s: ConnectionStore[WConn] = ConnectionStore(tmp_path / "c", WConn)
    cli = build_cli(s, name="myapp")
    assert cli.name == "myapp"


def test_build_cli_rejects_connection_class_kwarg(tmp_path: Path) -> None:
    from a2kit.scaffold import build_cli

    s: ConnectionStore[WConn] = ConnectionStore(tmp_path / "c", WConn)
    with pytest.raises(TypeError):
        build_cli(s, connection_class=WConn)  # type: ignore[call-arg]


def test_mcprunner_rejects_connection_class_kwarg(tmp_path: Path) -> None:
    s: ConnectionStore[WConn] = ConnectionStore(tmp_path / "c", WConn)
    with pytest.raises(TypeError):
        MCPRunner(_FakeServer(), connection_store=s, connection_class=WConn)  # type: ignore[call-arg]


def test_runner_no_writes_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """v0.4: `--writes` no longer parsed; treated as unknown flag."""
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--writes"])
    assert "writes" not in parsed


def test_runner_no_enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """v0.4: `--enable a,b` no longer parsed."""
    server = _FakeServer()
    parsed = MCPRunner(server).run(argv=["--enable", "a,b"])
    assert "enable" not in parsed


# ── v0.13 RunnerOptions ────────────────────────────────────────────────


def test_runner_options_basic() -> None:
    """`RunnerOptions(...)` skips argv round-tripping and produces the same
    parsed shape as the argv path."""
    from a2kit.scaffold import RunnerOptions

    server = _FakeServer()
    options = RunnerOptions(select_expr="default and not write", scope="prod")
    parsed = MCPRunner(server).run(options=options)
    assert parsed["scope"] == "prod"
    assert parsed["effective_select"] is not None


def test_runner_options_http_no_value() -> None:
    """`RunnerOptions(http="")` triggers HTTP transport with default host:port."""
    from a2kit.scaffold import RunnerOptions

    server = _FakeServer()
    MCPRunner(server).run(options=RunnerOptions(http=""))
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8080


def test_runner_options_http_host_port() -> None:
    """`RunnerOptions(http="0.0.0.0:9000")` parses host + port."""
    from a2kit.scaffold import RunnerOptions

    server = _FakeServer()
    MCPRunner(server).run(options=RunnerOptions(http="0.0.0.0:9000"))  # noqa: S104
    assert server.settings.host == "0.0.0.0"  # noqa: S104
    assert server.settings.port == 9000


def test_runner_options_transport_override() -> None:
    """`options.transport` is honoured when `transport=` kwarg is None."""
    from a2kit.scaffold import RunnerOptions

    server = _FakeServer()
    parsed = MCPRunner(server).run(options=RunnerOptions(transport="stdio"))
    # No HTTP options set + explicit stdio transport → host/port untouched.
    assert "http" in parsed


def test_runner_options_register(tmp_path: Path) -> None:
    """`RunnerOptions(registers=...)` reaches `register_args` like argv `--register`."""
    from a2kit.scaffold import RunnerOptions

    server = _FakeServer()
    store: ConnectionStore[WConn] = ConnectionStore(tmp_path / "c", WConn)
    parsed = MCPRunner(server, connection_store=store).run(options=RunnerOptions(registers=("ep url=https://x",)))
    assert parsed["ephemeral"]
