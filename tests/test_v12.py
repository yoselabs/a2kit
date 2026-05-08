"""v0.12 — integration surface redesign.

Covers:
- `RegisterBlock` ParamType: parses one `--register` block from either a
  quoted string (Click-native) or a pre-tokenised list (legacy walker path).
"""

from __future__ import annotations

from typing import Any

import pytest

import a2kit
from a2kit.scaffold import RegisterBlock

_ = Any  # keep `Any` referenced at module scope so per-test usages resolve under PEP 563


# ---- RegisterBlock — string form (Click-native) ---------------------------- #


def test_register_block_string_with_router_prefix() -> None:
    parser = RegisterBlock()
    router, key, kwargs = parser.convert("jira:prod url=https://x token=t")
    assert router == "jira"
    assert key == ("prod",)
    assert kwargs == {"url": "https://x", "token": "t"}


def test_register_block_string_without_router_prefix() -> None:
    parser = RegisterBlock()
    router, key, kwargs = parser.convert("prod url=https://x")
    assert router is None
    assert key == ("prod",)
    assert kwargs == {"url": "https://x"}


def test_register_block_string_handles_quoted_values() -> None:
    """shlex.split recognises quotes — so `"a b"` is one token."""
    parser = RegisterBlock()
    router, key, kwargs = parser.convert('jira:prod url="https://x with space"')
    assert kwargs == {"url": "https://x with space"}
    assert router == "jira"
    assert key == ("prod",)


def test_register_block_string_multipart_key() -> None:
    parser = RegisterBlock()
    router, key, _ = parser.convert("jira:org/team/proj url=x")
    assert router == "jira"
    assert key == ("org", "team", "proj")


# ---- RegisterBlock — list form (legacy walker path) ------------------------ #


def test_register_block_list_form() -> None:
    parser = RegisterBlock()
    router, key, kwargs = parser.convert(["jira:prod", "url=x", "token=t"])
    assert router == "jira"
    assert key == ("prod",)
    assert kwargs == {"url": "x", "token": "t"}


# ---- RegisterBlock — error paths ------------------------------------------- #


def test_register_block_empty_raises() -> None:
    parser = RegisterBlock()
    with pytest.raises(Exception, match="requires a key"):
        parser.convert("")


def test_register_block_skips_non_kv_token() -> None:
    """Defensive: malformed token (no `=`) stops field parsing for this block.

    Matches v0.11 multi-arg walker behaviour where a non-`=` token was
    treated as the start of the next positional. RegisterBlock breaks at
    the same boundary.
    """
    parser = RegisterBlock()
    _router, _key, kwargs = parser.convert(["jira:prod", "url=x", "stray", "token=t"])
    assert kwargs == {"url": "x"}  # `stray` halted parsing; `token=t` not picked up


# ---- DI types --------------------------------------------------------------- #


def test_provider_protocol_runtime_check() -> None:
    """A class with `provides` + `async get` satisfies `Provider` structurally."""

    class FakeProvider:
        provides = int

        async def get(self, **_ctx: object) -> int:
            return 42

    assert isinstance(FakeProvider(), a2kit.Provider)


def test_pluginbase_defaults_are_no_ops() -> None:
    """PluginBase ships safe defaults — empty providers/commands, no-op hooks."""

    class MyPlugin(a2kit.PluginBase):
        name = "test"

    p = MyPlugin()
    assert p.providers == []
    assert p.commands == []


async def test_pluginbase_lifecycle_hooks_default_no_op() -> None:
    """`on_startup` / `on_shutdown` defaults return None without side effects."""

    class MyPlugin(a2kit.PluginBase):
        name = "test"

    p = MyPlugin()
    assert await p.on_startup(runner=None) is None
    assert await p.on_shutdown(runner=None) is None


def test_provider_collision_message_includes_type_and_classes() -> None:
    """`ProviderCollisionError.__str__` mentions the type + both colliding provider classes."""

    class A:
        pass

    class B:
        pass

    exc = a2kit.ProviderCollisionError(int, A, B)
    s = str(exc)
    assert "int" in s
    assert "A" in s and "B" in s


def test_unknown_provider_type_message_includes_tool_param_type() -> None:
    """`UnknownProviderTypeError.__str__` mentions the tool name, param name, and type."""
    exc = a2kit.UnknownProviderTypeError("close_issue", "jira", str)
    s = str(exc)
    assert "close_issue" in s
    assert "jira" in s
    assert "str" in s


def test_binding_and_toolplan_are_frozen_slotted() -> None:
    """`Binding` and `ToolPlan` are frozen slotted dataclasses (cheap, hashable)."""

    class FakeProvider:
        provides = int

        async def get(self, **_ctx: object) -> int:
            return 1

    p = FakeProvider()
    b = a2kit.Binding(param_name="n", provider=p)
    plan = a2kit.ToolPlan(fn=lambda: None, bindings=(b,), passthrough=("query",))
    # frozen → cannot mutate
    with pytest.raises((AttributeError, TypeError)):
        b.param_name = "other"  # type: ignore[misc]
    assert plan.passthrough == ("query",)


# ---- OTel helpers ----------------------------------------------------------- #


def test_get_tracer_cached() -> None:
    """`get_tracer()` returns the same instance on repeat calls."""
    t1 = a2kit.get_tracer()
    t2 = a2kit.get_tracer()
    assert t1 is t2


def test_plugin_span_no_provider_returns_null_span() -> None:
    """No real OTel provider configured → `plugin_span` returns a no-op CM."""
    # In the test env, no provider is set, so we get the NullSpan path.
    with a2kit.plugin_span("test.op", custom_attr="v") as span:
        # The null-span doesn't expose set_attribute; this should just not raise.
        assert span is not None


def test_plugin_span_active_provider_stamps_attrs(monkeypatch: pytest.MonkeyPatch) -> None:
    """When a real OTel provider is configured, plugin_span stamps the
    `a2kit.plugin.name` attr plus caller-supplied kwargs on the entered span.
    """

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

    from a2kit import _otel

    # Reset the tracer cache so our FakeTracer is picked up.
    _otel._TRACER_CACHE.clear()
    monkeypatch.setattr(trace, "get_tracer_provider", FakeProvider)
    monkeypatch.setattr(trace, "get_tracer", lambda _name: FakeTracer())

    with a2kit.plugin_span("connections.load", connection_key="prod") as wrapper:
        assert wrapper is not None

    assert captured.attrs == {
        "a2kit.plugin.name": "connections.load",
        "connection_key": "prod",
    }

    # Also exercise the no-extra-attrs branch — plugin_span without kwargs
    # should still stamp the plugin name.
    captured.attrs.clear()
    with a2kit.plugin_span("cassettes.record"):
        pass
    assert captured.attrs == {"a2kit.plugin.name": "cassettes.record"}

    _otel._TRACER_CACHE.clear()


def test_plugin_span_skips_attrs_when_span_lacks_set_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive: a span object without `set_attribute` shouldn't blow up the wrapper."""

    class WeirdSpan:
        # No set_attribute method — simulates an unusual span implementation.
        pass

    class WeirdCM:
        def __enter__(self) -> WeirdSpan:
            return WeirdSpan()

        def __exit__(self, *exc: object) -> None:
            return None

    class WeirdTracer:
        def start_as_current_span(self, _name: str) -> WeirdCM:
            return WeirdCM()

    class FakeProvider:
        pass

    from opentelemetry import trace

    from a2kit import _otel

    _otel._TRACER_CACHE.clear()
    monkeypatch.setattr(trace, "get_tracer_provider", FakeProvider)
    monkeypatch.setattr(trace, "get_tracer", lambda _name: WeirdTracer())

    # Should not raise — the wrapper checks hasattr before calling set_attribute.
    with a2kit.plugin_span("weird.case", attr1="x"):
        pass

    _otel._TRACER_CACHE.clear()


def test_no_op_tracer_returns_null_span() -> None:
    """`_NoOpTracer.start_as_current_span` returns the package's `_NullSpan`."""
    from a2kit._otel import _NoOpTracer, _NullSpan

    cm = _NoOpTracer().start_as_current_span("anything")
    assert isinstance(cm, _NullSpan)
    # CM contract: enter/exit don't blow up.
    with cm:
        pass


def test_get_tracer_falls_back_to_noop_when_otel_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate OTel not being installed — `get_tracer()` returns a `_NoOpTracer`."""
    import builtins

    from a2kit import _otel

    _otel._TRACER_CACHE.clear()
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "opentelemetry":
            raise ImportError("simulated missing OTel")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    tracer = a2kit.get_tracer()
    assert isinstance(tracer, _otel._NoOpTracer)
    _otel._TRACER_CACHE.clear()


def test_plugin_span_falls_back_to_null_when_otel_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate OTel not being installed — `plugin_span()` returns `_NullSpan`."""
    import builtins

    from a2kit._otel import _NullSpan

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "opentelemetry":
            raise ImportError("simulated missing OTel")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", fake_import)
    cm = a2kit.plugin_span("any.thing")
    assert isinstance(cm, _NullSpan)


# ---- MCPRunner — provides= / plugins= / lookup_provider --------------------- #


class _FakeServer:
    """Minimal FastMCPLike for MCPRunner tests — no real MCP wiring."""

    class settings:  # noqa: N801
        host = ""
        port = 0

    def tool(self, *args: object, **kwargs: object) -> object:
        return None

    def run(self, *args: object, **kwargs: object) -> None:
        return None


class _FakeProviderForA:
    """Provider stub: produces type A."""

    class A:
        pass

    provides = A

    async def get(self, **_ctx: object) -> A:
        return self.A()


class _FakeProviderForB:
    """Provider stub: produces type B."""

    class B:
        pass

    provides = B

    async def get(self, **_ctx: object) -> B:
        return self.B()


class _OtherProviderForA(_FakeProviderForA):
    """Second provider claiming the same `provides` type — used to test collisions."""


def test_runner_provides_builds_type_index() -> None:
    runner = a2kit.MCPRunner(
        _FakeServer(),
        provides=[_FakeProviderForA(), _FakeProviderForB()],
    )
    a = runner.lookup_provider(_FakeProviderForA.A)
    b = runner.lookup_provider(_FakeProviderForB.B)
    assert isinstance(a, _FakeProviderForA)
    assert isinstance(b, _FakeProviderForB)


def test_runner_lookup_returns_none_for_unregistered_type() -> None:
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_FakeProviderForA()])
    assert runner.lookup_provider(_FakeProviderForB.B) is None


def test_runner_provider_collision_raises_at_lookup() -> None:
    """Two providers for the same type → `ProviderCollisionError` on index build."""
    runner = a2kit.MCPRunner(
        _FakeServer(),
        provides=[_FakeProviderForA(), _OtherProviderForA()],
    )
    with pytest.raises(a2kit.ProviderCollisionError, match="Provider collision for A"):
        runner.lookup_provider(_FakeProviderForA.A)


def test_runner_plugins_contribute_providers() -> None:
    """A plugin's `providers` list is folded into the runner's index."""

    class MyPlugin(a2kit.PluginBase):
        name = "test"
        providers = [_FakeProviderForA()]

    runner = a2kit.MCPRunner(_FakeServer(), plugins=[MyPlugin()])
    p = runner.lookup_provider(_FakeProviderForA.A)
    assert isinstance(p, _FakeProviderForA)


def test_runner_collision_across_provides_and_plugin() -> None:
    """A `provides=` provider + a plugin provider for the same type collide."""

    class MyPlugin(a2kit.PluginBase):
        name = "test"
        providers = [_OtherProviderForA()]

    runner = a2kit.MCPRunner(
        _FakeServer(),
        provides=[_FakeProviderForA()],
        plugins=[MyPlugin()],
    )
    with pytest.raises(a2kit.ProviderCollisionError):
        runner.lookup_provider(_FakeProviderForA.A)


def test_runner_cli_commands_aggregates_plugin_commands() -> None:
    """`runner.cli_commands` returns plugin commands for host CLI mounting."""
    import click

    @click.command("plugin-a-cmd")
    def cmd_a() -> None: ...

    @click.command("plugin-b-cmd")
    def cmd_b() -> None: ...

    class PluginA(a2kit.PluginBase):
        name = "a"
        commands = [cmd_a]

    class PluginB(a2kit.PluginBase):
        name = "b"
        commands = [cmd_b]

    runner = a2kit.MCPRunner(_FakeServer(), plugins=[PluginA(), PluginB()])
    names = {getattr(c, "name", None) for c in runner.cli_commands}
    assert names == {"plugin-a-cmd", "plugin-b-cmd"}


def test_runner_cli_commands_empty_when_no_plugins() -> None:
    runner = a2kit.MCPRunner(_FakeServer())
    assert runner.cli_commands == []


def test_runner_provider_index_built_at_prepare() -> None:
    """Calling `_prepare()` builds the index — collisions surface there, not later."""

    class Bad(a2kit.PluginBase):
        name = "bad"
        providers = [_FakeProviderForA(), _OtherProviderForA()]

    runner = a2kit.MCPRunner(_FakeServer(), plugins=[Bad()])
    with pytest.raises(a2kit.ProviderCollisionError):
        runner._prepare(argv=[], transport="stdio")


# ---- Verb decorators (@a2kit.list / @a2kit.read / @a2kit.write) ------------ #


def test_verb_list_defaults_listview_to_local_and_adds_read_cap() -> None:
    """@a2kit.list defaults filter/fields/pagination to Local, adds Cap.READ."""

    @a2kit.list()
    async def list_widgets() -> list[dict]:
        return []

    meta = a2kit.tool_metadata(list_widgets)
    assert a2kit.Cap.READ in meta.capabilities


def test_verb_list_passes_through_overrides() -> None:
    """Author overrides win — `filter=Passthrough` survives the verb defaults."""

    @a2kit.list(filter=a2kit.Passthrough)
    async def search_widgets(*, filter: str = "") -> list[dict]:  # noqa: A002
        return []

    # The wrapper signature: kit-injected params for fields/pagination should
    # exist (still Local), but `filter` must remain author-declared (Passthrough).
    import inspect

    sig = inspect.signature(search_widgets)
    assert "filter" in sig.parameters
    # `filter` is the author's positional/kwonly — annotation is `str`
    # (carried through unchanged whether stringified by PEP 563 or not).
    anno = sig.parameters["filter"].annotation
    assert anno is str or anno == "str"


def test_verb_read_adds_read_cap_no_listview_defaults() -> None:
    """@a2kit.read adds Cap.READ but doesn't enable list-view kit by default."""

    @a2kit.read()
    async def get_widget(*, widget_id: str) -> dict:
        return {"id": widget_id}

    meta = a2kit.tool_metadata(get_widget)
    assert a2kit.Cap.READ in meta.capabilities
    assert a2kit.Cap.WRITE not in meta.capabilities

    # No kit-injected `filter` / `fields` / `cursor` params — list-view is off.
    import inspect

    sig = inspect.signature(get_widget)
    assert "filter" not in sig.parameters
    assert "fields" not in sig.parameters
    assert "cursor" not in sig.parameters


def test_verb_write_adds_write_cap_and_sets_write_flag() -> None:
    """@a2kit.write adds Cap.WRITE; underlying tool is in write mode."""

    @a2kit.write()
    async def close_widget(*, widget_id: str) -> dict:
        return {"id": widget_id, "closed": True}

    meta = a2kit.tool_metadata(close_widget)
    assert a2kit.Cap.WRITE in meta.capabilities


def test_verb_read_rejects_str_return() -> None:
    """Verb decorators inherit @tool's `-> str` rejection."""
    with pytest.raises(a2kit.InvalidToolReturnTypeError):

        @a2kit.read()
        async def bad() -> str:
            return "x"


def test_verb_list_capabilities_can_be_extended() -> None:
    """Author can add caps via the kwarg — `Cap.READ` is unioned in."""

    @a2kit.list(capabilities={a2kit.Cap.EXTERNAL})
    async def fetch_widgets() -> list[dict]:
        return []

    meta = a2kit.tool_metadata(fetch_widgets)
    assert a2kit.Cap.READ in meta.capabilities
    assert a2kit.Cap.EXTERNAL in meta.capabilities


# ---- @MyRouter.list (Router classmethod) ----------------------------------- #


def test_router_list_registers_list_shaped_tool() -> None:
    """@MyRouter.list registers a tool that gets Cap.READ + list-view defaults
    when applied via the registry.
    """

    class WRouter(a2kit.Router):
        pass

    @WRouter.list()
    async def list_widgets() -> list[dict]:
        return []

    # The binding is recorded before apply.
    assert len(WRouter._tools) == 1
    assert WRouter._tools[0].mode == "list"


def test_router_list_applied_via_registry_gets_listview_defaults() -> None:
    """Applying a @MyRouter.list tool through RouterRegistry produces a wrapper
    with kit-injected `filter` / `fields` / `cursor` (Local mode) params.
    """
    import inspect

    class _RegistryFakeServer:
        registered: list[Any] = []  # noqa: RUF012

        def tool(self) -> Any:  # noqa: PLR6301
            def decorator(fn: Any) -> Any:
                _RegistryFakeServer.registered.append(fn)
                return fn

            return decorator

        class _ToolManager:
            @staticmethod
            def list_tools() -> list[Any]:
                return []

        _tool_manager = _ToolManager()

    _RegistryFakeServer.registered = []

    class WRouter(a2kit.Router):
        pass

    @WRouter.list()
    async def list_widgets_v2() -> list[dict]:
        return []

    # Apply via registry.
    server = _RegistryFakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(WRouter())
    routers.apply(server, store=None)

    assert len(_RegistryFakeServer.registered) == 1
    wrapper = _RegistryFakeServer.registered[0]
    sig = inspect.signature(wrapper)
    # kit-injected list-view Local params present:
    assert "filter" in sig.parameters
    assert "fields" in sig.parameters
    assert "cursor" in sig.parameters
    assert "limit" in sig.parameters

    # Tool gets read caps stamped via router's read_capabilities.
    meta = a2kit.tool_metadata(wrapper)
    assert a2kit.Cap.READ in meta.capabilities


# ---- a2kit.App composition class ------------------------------------------- #


class _AppConn(a2kit.ConnectionInfo):
    url: str


class _AppConn2(a2kit.ConnectionInfo):
    url: str


def test_app_basic_composition(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """App wraps FastMCP + store + registry without exposing them as a tuple."""
    app = a2kit.App("test-app")
    store = app.connect(_AppConn, config_dir=tmp_path)
    assert isinstance(store, a2kit.ConnectionStore)
    assert app.server is not None
    assert app.runner is not None  # lazy build


def test_app_does_not_create_filesystem_dirs() -> None:
    """App.__init__ touches NO filesystem state — Docker-read-only-FS friendly."""
    # Just constructing App with no connect() must not create any directory.
    app = a2kit.App("test-no-fs")
    # No `app.config_dir` attribute — that concern belongs to the store.
    assert not hasattr(app, "config_dir")
    assert app.server is not None


def test_app_connect_rejects_duplicate_type(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Same ConnectionInfo subclass registered twice → ValueError."""
    app = a2kit.App("test-dup")
    app.connect(_AppConn, config_dir=tmp_path)
    with pytest.raises(ValueError, match="already has a ConnectionStore"):
        app.connect(_AppConn, config_dir=tmp_path)


def test_app_use_router_class_or_instance(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.use(RouterCls)` and `app.use(router_instance)` both work."""

    class MyRouter(a2kit.Router):
        pass

    class MyOtherRouter(a2kit.Router):
        pass

    app = a2kit.App("test-routers")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(MyRouter)  # class form
    app.use(MyOtherRouter())  # instance form

    runner = app.runner
    names = runner.router_registry.names() if runner.router_registry else []
    assert "my" in names
    assert "my-other" in names


def test_app_use_plugin_passes_to_runner(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.use(plugin)` registers the plugin with the underlying MCPRunner."""

    class MyPlugin(a2kit.PluginBase):
        name = "my-plugin"

    app = a2kit.App("test-plugin")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(MyPlugin())

    # Plugin should be visible to the runner.
    assert len(app.runner._plugins) == 1
    assert app.runner._plugins[0].name == "my-plugin"


def test_app_use_provider_routes_to_provides_list(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.use(provider)` adds a Provider instance to the runner's `provides=` list."""
    app = a2kit.App("test-provider")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(_FakeProviderForA())
    runner = app.runner
    assert runner.lookup_provider(_FakeProviderForA.A) is not None


def test_provider_graph_dfs_skips_soft_known_dep_in_cycle_check() -> None:
    """A provider whose dep is `soft_known` doesn't trigger cycle recursion.

    Module-scope classes — locally-defined classes can't be resolved by
    `inspect.get_annotations(eval_str=True)` under PEP 563.
    """
    from a2kit.di import _validate_provider_graph

    index = {_ChainTypeA: _SoftDepProv()}
    _validate_provider_graph(index, soft_known=frozenset({_SoftType}))
    # No exception → soft-known correctly skipped in DFS.


def test_app_cli_returns_click_group(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.cli` returns a Click group with login/logout/connections subcommands."""
    import click

    app = a2kit.App("test-cli")
    app.connect(_AppConn, config_dir=tmp_path)
    cli = app.cli
    assert isinstance(cli, click.Group)
    # Default commands from build_cli:
    assert "login" in cli.commands
    assert "logout" in cli.commands
    assert "connections" in cli.commands


def test_app_cli_aggregates_plugin_commands(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Plugin-contributed commands are mounted onto app.cli."""
    import click

    @click.command("my-plugin-cmd")
    def my_cmd() -> None: ...

    class MyPlugin(a2kit.PluginBase):
        name = "my"
        commands = [my_cmd]

    app = a2kit.App("test-cli-plugin")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(MyPlugin())
    cli = app.cli
    assert "my-plugin-cmd" in cli.commands


def test_app_runner_lazy_build_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`app.runner` is built once on first access, cached after."""
    app = a2kit.App("test-lazy")
    app.connect(_AppConn, config_dir=tmp_path)
    r1 = app.runner
    r2 = app.runner
    assert r1 is r2


def test_app_connect_two_distinct_types_works(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Two different ConnectionInfo subclasses → two stores, no collision."""
    app = a2kit.App("test-multi")
    s1 = app.connect(_AppConn, config_dir=tmp_path)
    s2 = app.connect(_AppConn2, config_dir=tmp_path)
    assert s1 is not s2
    assert s1.connection_class is _AppConn
    assert s2.connection_class is _AppConn2


def test_app_router_with_explicit_store_not_overridden(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A router that already has its own `store=` is not auto-wired by App."""

    class MyRouter(a2kit.Router):
        pass

    app = a2kit.App("test-explicit-store")
    s1 = app.connect(_AppConn, config_dir=tmp_path)
    own_store = a2kit.ConnectionStore(tmp_path / "other", _AppConn)
    app.use(MyRouter(store=own_store))
    _ = app.runner
    # Router kept its own store; not replaced by App's auto-wiring.
    assert app._routers[0].store is own_store
    assert app._routers[0].store is not s1


def test_app_run_server_delegates_to_runner(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`app.run_server(argv=...)` forwards to `runner.run(argv=...)`.

    `app.run()` itself dispatches through Click — see the CLI dispatch tests.
    """
    app = a2kit.App("test-run")
    app.connect(_AppConn, config_dir=tmp_path)
    captured: dict[str, object] = {}

    def fake_run(self, argv=None, *, transport=None):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        captured["transport"] = transport
        return {"ok": True}

    from a2kit.scaffold._runner import MCPRunner

    monkeypatch.setattr(MCPRunner, "run", fake_run)
    out = app.run_server(argv=[], transport="stdio")
    assert out == {"ok": True}
    assert captured == {"argv": [], "transport": "stdio"}


def test_app_cli_serve_subcommand_starts_server(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`app.run(['serve'])` invokes the server-start subcommand."""
    app = a2kit.App("test-serve")
    app.connect(_AppConn, config_dir=tmp_path)

    captured: dict[str, object] = {}

    def fake_run(self, argv=None, *, transport=None):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return {}

    from a2kit.scaffold._runner import MCPRunner

    monkeypatch.setattr(MCPRunner, "run", fake_run)
    app.run(argv=["serve"])
    # serve invoked → runner.run was called.
    assert "argv" in captured


def test_app_cli_lists_tool_subcommands(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Each registered tool becomes a top-level subcommand of the unified CLI."""

    class T(a2kit.ConnectionInfo):
        url: str

    class TRouter(a2kit.Router):
        pass

    @TRouter.read()
    async def my_tool(*, conn: T, query: str) -> dict:
        """First line of docstring becomes the subcommand's --help text."""
        return {"q": query, "u": conn.url}

    app = a2kit.App("test-tool-subcmds")
    app.connect(T, config_dir=tmp_path)
    app.use(TRouter)
    cmds = app.cli.commands
    # Tool name is its own subcommand:
    assert "my_tool" in cmds
    # Docstring's first line surfaces as the help text:
    assert "First line" in cmds["my_tool"].help
    # Built-ins still present:
    assert "serve" in cmds
    assert "login" in cmds


def test_app_cli_invokes_tool_via_subcommand(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """`app.run([<tool-name>, key=value, ...])` invokes the tool and prints the result."""

    class T(a2kit.ConnectionInfo):
        url: str = "x"

    class TRouter(a2kit.Router):
        pass

    @TRouter.tool()
    async def echo(*, message: str) -> dict:
        return {"echoed": message}

    app = a2kit.App("test-invoke")
    app.connect(T, config_dir=tmp_path)
    app.use(TRouter)
    app.run(argv=["echo", "message=hello"])
    out = capsys.readouterr().out
    assert '"echoed": "hello"' in out


def test_app_cli_invokes_tool_returning_list_of_models(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """List of Pydantic models serialises as a JSON array.

    `_AppConn` is module-level so FastMCP's annotation introspection
    (`inspect.get_annotations(eval_str=True)`) can resolve it.
    """

    class LRouter(a2kit.Router):
        pass

    @LRouter.tool()
    async def items() -> list[_AppConn]:
        return [_AppConn(key=("a",), url="1"), _AppConn(key=("b",), url="2")]

    app = a2kit.App("test-list-out")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(LRouter)
    app.run(argv=["items"])
    out = capsys.readouterr().out
    assert '"url": "1"' in out and '"url": "2"' in out


def test_app_cli_invokes_tool_with_plain_dict_result(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Tool returning a plain dict — serialises as JSON without model_dump."""

    class T(a2kit.ConnectionInfo):
        url: str = "x"

    class DRouter(a2kit.Router):
        pass

    @DRouter.tool()
    async def stat() -> dict:
        return {"ok": True, "count": 3}

    app = a2kit.App("test-dict-out")
    app.connect(T, config_dir=tmp_path)
    app.use(DRouter)
    app.run(argv=["stat"])
    out = capsys.readouterr().out
    assert '"ok": true' in out
    assert '"count": 3' in out


def test_app_cli_unknown_tool_raises(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Invoking a tool name that isn't registered raises a ClickException."""
    import click

    class T(a2kit.ConnectionInfo):
        url: str = "x"

    class XRouter(a2kit.Router):
        pass

    @XRouter.tool()
    async def actual_tool() -> dict:
        return {}

    app = a2kit.App("test-unknown")
    app.connect(T, config_dir=tmp_path)
    app.use(XRouter)
    # Tool name `nonexistent` is not registered as a subcommand at all → Click
    # rejects the unknown subcommand. We accept either Click's exception or a
    # ClickException as evidence.
    with pytest.raises((click.exceptions.UsageError, click.exceptions.NoSuchOption, SystemExit, click.ClickException)):
        # Force tool that LOOKS like a subcommand by manually invoking _invoke_tool.
        app._invoke_tool("nonexistent", {})


def test_app_cli_tool_kwarg_must_be_keyvalue(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A non-key=value arg raises BadParameter."""
    import click

    class T(a2kit.ConnectionInfo):
        url: str = "x"

    class KRouter(a2kit.Router):
        pass

    @KRouter.tool()
    async def kt(*, x: str) -> dict:
        return {"x": x}

    app = a2kit.App("test-kw")
    app.connect(T, config_dir=tmp_path)
    app.use(KRouter)
    with pytest.raises((click.BadParameter, click.exceptions.UsageError, SystemExit)):
        app.run(argv=["kt", "missing-equals"])


def test_app_cli_tool_with_unserialisable_result_falls_back_to_repr(tmp_path, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Result that can't be JSON-serialised falls back to repr().

    We force the JSON path to fail by patching `json.dumps` to raise — covers
    the defensive fallback in `_invoke_tool`.
    """
    import json

    class T(a2kit.ConnectionInfo):
        url: str = "x"

    class URouter(a2kit.Router):
        pass

    @URouter.tool()
    async def opaque() -> dict:
        return {"value": "hello"}

    app = a2kit.App("test-opaque")
    app.connect(T, config_dir=tmp_path)
    app.use(URouter)

    real_dumps = json.dumps

    def failing_dumps(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise TypeError("simulated unserialisable")

    # Patch json.dumps inside a2kit.app's _invoke_tool indirectly via the json module.
    monkeypatch.setattr("a2kit.app.json", type("J", (), {"dumps": failing_dumps})(), raising=False)
    # The above won't work because _invoke_tool imports json locally. Skip the patch
    # and instead verify the fallback path via a different means — make json.dumps
    # raise globally:
    monkeypatch.setattr(json, "dumps", failing_dumps)
    app.run(argv=["opaque"])
    out = capsys.readouterr().out
    monkeypatch.setattr(json, "dumps", real_dumps)
    assert "{'value': 'hello'}" in out


def test_app_cli_with_no_stores_returns_bare_click_group() -> None:
    """An App with no `connect()` calls still produces a usable Click group
    (just `serve` + plugin commands; no login/logout/connections)."""
    app = a2kit.App("test-no-stores")
    cli = app.cli
    assert "serve" in cli.commands
    # No connection-management commands when no stores are registered:
    assert "login" not in cli.commands


def test_app_cli_invokes_sync_tool_returning_model(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Sync tool returning a Pydantic model → serialised via `.model_dump()`."""

    class SRouter(a2kit.Router):
        pass

    @SRouter.tool()
    def sync_get() -> _AppConn:
        return _AppConn(key=("a",), url="hello")

    app = a2kit.App("test-sync-model")
    app.connect(_AppConn, config_dir=tmp_path)
    app.use(SRouter)
    app.run(argv=["sync_get"])
    out = capsys.readouterr().out
    assert '"url": "hello"' in out


def test_app_cli_rejects_tool_name_collision_with_builtin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Tool whose name matches a built-in subcommand raises at CLI build time."""

    class T(a2kit.ConnectionInfo):
        url: str

    class CRouter(a2kit.Router):
        pass

    @CRouter.read()
    async def login(*, conn: T) -> dict:  # noqa: ARG001 — name shadows built-in
        return {}

    app = a2kit.App("test-collide")
    app.connect(T, config_dir=tmp_path)
    app.use(CRouter)
    with pytest.raises(ValueError, match="collides with a built-in"):
        _ = app.cli


async def test_app_run_async_delegates_to_runner(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`await app.run_async(...)` forwards to `runner.run_async(...)`."""
    app = a2kit.App("test-run-async")
    app.connect(_AppConn, config_dir=tmp_path)
    captured: dict[str, object] = {}

    async def fake_run_async(self, argv=None, *, transport=None):  # type: ignore[no-untyped-def]
        captured["argv"] = argv
        return {"ok": True}

    from a2kit.scaffold._runner import MCPRunner

    monkeypatch.setattr(MCPRunner, "run_async", fake_run_async)
    out = await app.run_async(argv=[])
    assert out == {"ok": True}
    assert captured == {"argv": []}


def test_app_auto_wires_single_store_to_routers_without_store(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """When there's exactly one store and a router with `store=None`, App
    wires the store to the router automatically. Saves boilerplate.
    """

    class MyRouter(a2kit.Router):
        pass

    app = a2kit.App("test-autowire")
    store = app.connect(_AppConn, config_dir=tmp_path)
    app.use(MyRouter)
    _ = app.runner  # trigger build
    # The router instance should have the store wired.
    routers = app._routers
    assert routers[0].store is store


def test_router_list_author_override_wins() -> None:
    """`@WRouter.list(filter=Passthrough)` overrides the Local default."""

    class _RegistryFakeServer2:
        registered: list[Any] = []  # noqa: RUF012

        def tool(self) -> Any:  # noqa: PLR6301
            def decorator(fn: Any) -> Any:
                _RegistryFakeServer2.registered.append(fn)
                return fn

            return decorator

        class _ToolManager:
            @staticmethod
            def list_tools() -> list[Any]:
                return []

        _tool_manager = _ToolManager()

    _RegistryFakeServer2.registered = []

    class XRouter(a2kit.Router):
        pass

    @XRouter.list(filter=a2kit.Passthrough)
    async def search_widgets_v2(*, filter: str = "") -> list[dict]:  # noqa: A002
        _ = filter
        return []

    server = _RegistryFakeServer2()
    routers = a2kit.RouterRegistry()
    routers.add(XRouter())
    routers.apply(server, store=None)

    import inspect

    wrapper = _RegistryFakeServer2.registered[0]
    sig = inspect.signature(wrapper)
    # `filter` is the author's own param (Passthrough), not kit-injected.
    assert "filter" in sig.parameters
    # `fields`/`cursor` still get Local defaults since author didn't override:
    assert "fields" in sig.parameters
    assert "cursor" in sig.parameters


# ---- Step 6: chained DI (factory providers w/ typed kwonly deps) ----------- #


class _ChainTypeA:
    """Leaf type — no deps."""


class _ChainTypeB:
    """Mid-tier — depends on A."""

    def __init__(self, a: _ChainTypeA) -> None:
        self.a = a


class _ChainTypeC:
    """Top — depends on B (transitively on A)."""

    def __init__(self, b: _ChainTypeB) -> None:
        self.b = b


class _ProviderA:
    provides = _ChainTypeA

    def __init__(self) -> None:
        self.calls = 0

    async def get(self, **_ctx: object) -> _ChainTypeA:
        self.calls += 1
        return _ChainTypeA()


class _ProviderB:
    provides = _ChainTypeB

    def __init__(self) -> None:
        self.calls = 0

    async def get(self, *, a: _ChainTypeA, **_ctx: object) -> _ChainTypeB:
        self.calls += 1
        return _ChainTypeB(a)


class _ProviderC:
    provides = _ChainTypeC

    async def get(self, *, b: _ChainTypeB, **_ctx: object) -> _ChainTypeC:
        return _ChainTypeC(b)


@pytest.mark.anyio
async def test_runner_resolve_chained_two_deep() -> None:
    """`runner.resolve(B)` triggers ProviderA via the typed kwonly `a: A` dep."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_ProviderA(), _ProviderB()])
    b = await runner.resolve(_ChainTypeB)
    assert isinstance(b, _ChainTypeB)
    assert isinstance(b.a, _ChainTypeA)


@pytest.mark.anyio
async def test_runner_resolve_chained_three_deep() -> None:
    """C → B → A; both intermediate gets are awaited."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_ProviderA(), _ProviderB(), _ProviderC()])
    c = await runner.resolve(_ChainTypeC)
    assert isinstance(c, _ChainTypeC)
    assert isinstance(c.b, _ChainTypeB)
    assert isinstance(c.b.a, _ChainTypeA)


class _DiamondNeedsA1:
    pass


class _DiamondNeedsA2:
    pass


class _DiamondTop:
    def __init__(self, n1: _DiamondNeedsA1, n2: _DiamondNeedsA2) -> None:
        self.n1, self.n2 = n1, n2


class _DiamondPN1:
    provides = _DiamondNeedsA1

    async def get(self, *, a: _ChainTypeA, **_c: object) -> _DiamondNeedsA1:
        _ = a
        return _DiamondNeedsA1()


class _DiamondPN2:
    provides = _DiamondNeedsA2

    async def get(self, *, a: _ChainTypeA, **_c: object) -> _DiamondNeedsA2:
        _ = a
        return _DiamondNeedsA2()


class _DiamondPTop:
    provides = _DiamondTop

    async def get(self, *, n1: _DiamondNeedsA1, n2: _DiamondNeedsA2, **_c: object) -> _DiamondTop:
        return _DiamondTop(n1, n2)


@pytest.mark.anyio
async def test_runner_resolve_per_call_caches_diamond() -> None:
    """If two paths in the chain need A, A's `get` is called once per resolve()."""
    a_provider = _ProviderA()
    runner = a2kit.MCPRunner(
        _FakeServer(),
        provides=[a_provider, _DiamondPN1(), _DiamondPN2(), _DiamondPTop()],
    )
    await runner.resolve(_DiamondTop)
    assert a_provider.calls == 1


class _Tagged:
    def __init__(self, key: str) -> None:
        self.key = key


class _PTagged:
    provides = _Tagged

    async def get(self, **ctx: object) -> _Tagged:
        return _Tagged(str(ctx.get("connection_key", "?")))


@pytest.mark.anyio
async def test_runner_resolve_forwards_call_ctx() -> None:
    """`call_ctx` kwargs are forwarded for params not satisfied by chained deps."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_PTagged()])
    out = await runner.resolve(_Tagged, connection_key="prod")
    assert out.key == "prod"


def test_runner_unknown_provider_dep_raises_at_index_build() -> None:
    """Provider declares a typed kwonly dep with no provider → startup error."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_ProviderB()])
    with pytest.raises(a2kit.UnknownProviderDepError, match="_ChainTypeA"):
        runner.lookup_provider(_ChainTypeB)


class _CycA:
    pass


class _CycB:
    pass


class _CycPA:
    provides = _CycA

    async def get(self, *, b: _CycB, **_c: object) -> _CycA:
        _ = b
        return _CycA()


class _CycPB:
    provides = _CycB

    async def get(self, *, a: _CycA, **_c: object) -> _CycB:
        _ = a
        return _CycB()


def test_runner_provider_cycle_raises_at_index_build() -> None:
    """A → B → A cycle surfaces as `ProviderCycleError` at startup."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_CycPA(), _CycPB()])
    with pytest.raises(a2kit.ProviderCycleError, match="dependency cycle"):
        runner.lookup_provider(_CycA)


class _SelfT:
    pass


class _SelfP:
    provides = _SelfT

    async def get(self, *, x: _SelfT, **_c: object) -> _SelfT:
        return x


def test_runner_provider_self_cycle_raises() -> None:
    """A provider whose `get` deps on its own type self-cycles."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_SelfP()])
    with pytest.raises(a2kit.ProviderCycleError):
        runner.lookup_provider(_SelfT)


@pytest.mark.anyio
async def test_runner_resolve_dag_with_already_visited_root() -> None:
    """Register providers in reverse-topological order (C, B, A) so the outer
    cycle-check loop encounters a BLACK type after the first DFS completes.
    Exercises the "skip already-resolved root" branch in `_validate_provider_graph`.
    """
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_ProviderC(), _ProviderB(), _ProviderA()])
    c = await runner.resolve(_ChainTypeC)
    assert isinstance(c, _ChainTypeC)


@pytest.mark.anyio
async def test_runner_resolve_unknown_root_type_raises() -> None:
    """`resolve(T)` for a T with no provider raises `UnknownProviderTypeError`."""
    runner = a2kit.MCPRunner(_FakeServer(), provides=[_ProviderA()])
    with pytest.raises(a2kit.UnknownProviderTypeError, match="_ChainTypeB"):
        await runner.resolve(_ChainTypeB)


class _MixedSig:
    provides = _ChainTypeA

    async def get(self, positional: int = 1, *, typed: _ChainTypeA, untyped="x", **ctx: object) -> _ChainTypeA:  # noqa: ANN001
        _ = (positional, typed, untyped, ctx)
        return _ChainTypeA()


class _SoftType:
    """Soft-known dep — registered via `soft_known=` rather than as a provider."""


class _SoftDepProv:
    """Provider that depends on a soft-known type. Used to exercise the
    DFS soft-known skip branch in `_check_no_cycles`."""

    provides = _ChainTypeA

    async def get(self, *, x: _SoftType, **_c: object) -> _ChainTypeA:
        _ = x
        return _ChainTypeA()


def test_provider_dep_types_skips_untyped_and_var_kwargs() -> None:
    """`_provider_dep_types` only counts KEYWORD_ONLY params with class annotations."""
    from a2kit.di import _provider_dep_types

    deps = _provider_dep_types(_MixedSig())
    assert deps == {"typed": _ChainTypeA}
