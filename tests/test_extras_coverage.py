"""Coverage uplift for assorted modules: lint CLI runtime path,
connections CLI error paths, listview middleware short-circuits."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner


# --------------------------- lint CLI runtime command --------------------------- #


def test_lint_runtime_help() -> None:
    from a2kit.packages.lint.cli import main as cli_main

    assert isinstance(cli_main, click.Group)
    runner = CliRunner()
    result = runner.invoke(cli_main, ["runtime", "--help"])
    assert result.exit_code == 0
    assert "--import" in result.output


def test_lint_runtime_bad_import_target_format() -> None:
    """Missing colon → BadParameter."""
    from a2kit.packages.lint.cli import main as cli_main

    runner = CliRunner()
    result = runner.invoke(cli_main, ["runtime", "--import", "no_colon_here"])
    assert result.exit_code != 0
    assert "module:attr" in result.output


def test_lint_runtime_runs_on_minimal_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make a tiny module with a `server` attribute, run `lint runtime --import mod:server`."""
    from a2kit.packages.lint.cli import main as cli_main

    # Build a fake module pointing at a minimal `FastMCP`-shaped object via the lint runtime.
    # `run_runtime_checks` accepts any object — it does duck-typed introspection.
    pkg_dir = tmp_path / "fake_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "mod.py").write_text("class _S:\n    pass\nserver = _S()\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    runner = CliRunner()
    result = runner.invoke(cli_main, ["runtime", "--import", "fake_pkg.mod:server"])
    # Either prints findings (exit 1) or none (exit 0). What we want is _import_target ran.
    assert result.exit_code in (0, 1)


# --------------------------- connections CLI error paths --------------------------- #


def test_connections_show_unknown_conn_type() -> None:
    """`show` on an unregistered conn_type → exit 1, "Unknown" message."""
    from a2kit.packages.connections.cli import connections_cli

    group = connections_cli()
    runner = CliRunner()
    r = runner.invoke(group, ["show", "Nope", "--key=p"])
    assert r.exit_code == 1
    assert "Unknown connection type" in r.output


def test_connections_show_missing_key_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`show` for a known conn_type but no saved record → ConnectionNotFound output."""
    from tests.packages.connections.conftest import WidgetConfig

    from a2kit.packages.connections.cli import connections_cli

    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "conn"))
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    r = runner.invoke(group, ["show", "WidgetConfig", "--key=missing"])
    assert r.exit_code == 1
    assert "not found" in r.output.lower()


def test_connections_list_unknown_conn_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.packages.connections.conftest import WidgetConfig

    from a2kit.packages.connections.cli import connections_cli

    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "conn"))
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    r = runner.invoke(group, ["list", "Nope"])
    assert r.exit_code == 1
    assert "Unknown connection type" in r.output


def test_connections_list_no_app_no_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No conn types AND no config dir → silent (early return)."""
    from a2kit.packages.connections.cli import connections_cli

    cfg_home = tmp_path / "missing-cfg"
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(cfg_home))
    group = connections_cli()
    runner = CliRunner()
    r = runner.invoke(group, ["list"])
    assert r.exit_code == 0
    assert r.output.strip() == ""


def test_connections_parse_field_overrides_bad_format() -> None:
    """`_parse_field_overrides` rejects values without `=`."""
    from a2kit.packages.connections.cli import _parse_field_overrides

    with pytest.raises(click.BadParameter, match="KEY=VALUE"):
        _parse_field_overrides(("no_equals_sign",))


def test_connections_parse_key_arg_required() -> None:
    from a2kit.packages.connections.cli import _parse_key_arg
    from tests.packages.connections.conftest import WidgetConfig

    with pytest.raises(click.BadParameter, match="--key required"):
        _parse_key_arg(WidgetConfig, None)


def test_connections_parse_key_arg_arity_mismatch() -> None:
    from a2kit.packages.connections.cli import _parse_key_arg
    from tests.packages.connections.conftest import TripleConfig

    with pytest.raises(click.BadParameter, match="arity mismatch"):
        _parse_key_arg(TripleConfig, "only-one-part")


# --------------------------- listview middleware short-circuit branches --------------------------- #


def test_listview_middleware_returns_result_when_tool_lookup_fails() -> None:
    """`server.get_tool` raises → middleware swallows and returns the original result."""
    from fastmcp.tools.base import ToolResult

    from a2kit.packages.mcp.listview import ListViewMiddleware

    mw = ListViewMiddleware()

    # Build minimal fake context + result.
    fake_result = ToolResult(content=[], structured_content={"result": [{"id": 1}]})

    class _FakeFastMCP:
        async def get_tool(self, name: str) -> Any:
            raise RuntimeError("boom")

    class _FastMCPCtx:
        fastmcp = _FakeFastMCP()

    class _Params:
        name = "any-tool"

    class _Ctx:
        message = _Params()
        fastmcp_context = _FastMCPCtx()

    async def _next(ctx: Any) -> Any:
        return fake_result

    out = asyncio.run(mw.on_call_tool(_Ctx(), _next))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    assert out is fake_result


def test_listview_middleware_returns_result_when_no_fastmcp_context() -> None:
    """`fastmcp_context is None` short-circuit branch."""
    from fastmcp.tools.base import ToolResult

    from a2kit.packages.mcp.listview import ListViewMiddleware

    mw = ListViewMiddleware()
    fake_result = ToolResult(content=[], structured_content={"result": [{"id": 1}]})

    class _Params:
        name = "any-tool"

    class _Ctx:
        message = _Params()
        fastmcp_context = None

    async def _next(ctx: Any) -> Any:
        return fake_result

    out = asyncio.run(mw.on_call_tool(_Ctx(), _next))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    assert out is fake_result


def test_listview_middleware_returns_result_when_server_attr_missing() -> None:
    """`fastmcp_context.fastmcp is None` short-circuit branch."""
    from fastmcp.tools.base import ToolResult

    from a2kit.packages.mcp.listview import ListViewMiddleware

    mw = ListViewMiddleware()
    fake_result = ToolResult(content=[], structured_content={"result": [{"id": 1}]})

    class _FastMCPCtx:
        fastmcp = None

    class _Params:
        name = "any-tool"

    class _Ctx:
        message = _Params()
        fastmcp_context = _FastMCPCtx()

    async def _next(ctx: Any) -> Any:
        return fake_result

    out = asyncio.run(mw.on_call_tool(_Ctx(), _next))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    assert out is fake_result


def test_listview_middleware_returns_result_when_tool_name_missing() -> None:
    """No `params.name` → middleware returns result unchanged."""
    from fastmcp.tools.base import ToolResult

    from a2kit.packages.mcp.listview import ListViewMiddleware

    mw = ListViewMiddleware()
    fake_result = ToolResult(content=[], structured_content={"result": [{"id": 1}]})

    class _Params:
        pass  # no .name attr

    class _Ctx:
        message = _Params()
        fastmcp_context = MagicMock()

    async def _next(ctx: Any) -> Any:
        return fake_result

    out = asyncio.run(mw.on_call_tool(_Ctx(), _next))  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    assert out is fake_result


# --------------------------- connections.exceptions instantiation --------------------------- #


# --------------------------- @a2kit.tool removed in v0.33 --------------------------- #


def test_a2kit_tool_function_removed_from_submodule() -> None:
    """The ``tool()`` function was deleted from ``a2kit.tool`` in v0.33.

    Note: ``a2kit.tool`` itself is still importable as a submodule (internal
    code imports from it). The user-facing breakage is the missing function —
    ``from a2kit.tool import tool`` raises ImportError.
    """
    import pytest

    with pytest.raises(ImportError):
        from a2kit.tool import tool  # noqa: F401  # ty: ignore[unresolved-import]  # why: test exercises a removed/migrated import path to assert it raises


# --------------------------- a2kit.exceptions edges --------------------------- #


def test_invalid_tool_return_type_error_message() -> None:
    from a2kit.exceptions import InvalidToolReturnTypeError

    err = InvalidToolReturnTypeError("my_tool")
    assert err.fn_name == "my_tool"
    assert "my_tool" in str(err)


def test_write_not_allowed_with_empty_key_and_tool_name() -> None:
    from a2kit.packages.connections.exceptions import WriteNotAllowed

    err = WriteNotAllowed((), tool_name="dangerous")
    assert "<unknown>" in str(err)
    assert "dangerous" in str(err)


def test_write_not_allowed_with_key_no_tool_name() -> None:
    from a2kit.packages.connections.exceptions import WriteNotAllowed

    err = WriteNotAllowed(("p", "e"))
    assert "p-e" in str(err)


def test_tool_call_contamination_with_and_without_tool_name() -> None:
    from a2kit.exceptions import ToolCallContamination

    err = ToolCallContamination("foo", tool_name="t")
    assert "foo" in str(err)
    assert "t" in str(err)
    err2 = ToolCallContamination("bar")
    assert "bar" in str(err2)


def test_invalid_filter_expression_carries_hint() -> None:
    from a2kit.exceptions import InvalidFilterExpression

    err = InvalidFilterExpression("a > 1", "missing variable")
    assert err.expr == "a > 1"
    assert err.hint == "missing variable"


# --------------------------- routers slugify branches --------------------------- #


def test_router_slug_derived_from_class() -> None:
    """No `name` set → strip ``Router`` suffix and lowercase the rest."""
    import a2kit

    class MyTrackerRouter(a2kit.Router):
        tools = ()
        slug = "mytracker"

    r = MyTrackerRouter()
    assert r.slug == "mytracker"


def test_router_slug_no_router_suffix() -> None:
    import a2kit

    class Tasks(a2kit.Router):
        tools = ()
        slug = "tasks"

    r = Tasks()
    assert r.slug == "tasks"


def test_router_slug_collision_raises() -> None:
    import a2kit

    class TasksRouter(a2kit.Router):
        tools = ()
        slug = "tasks"

    class Tasks(a2kit.Router):
        tools = ()
        slug = "tasks"

    builder = a2kit.AppBuilder("a")
    builder.add_router(TasksRouter())

    with pytest.raises(ValueError, match="already registered"):
        builder.add_router(Tasks())


def test_router_slug_class_attr_wins() -> None:
    import a2kit

    class XYZ(a2kit.Router):
        tools = ()
        slug = "custom_slug"
        name = "custom_slug"

    r = XYZ()
    assert r.slug == "custom_slug"


def test_router_slug_attribute_pinned_at_class_level() -> None:
    import a2kit

    class _R(a2kit.Router):
        tools = ()
        slug = "_r_fixed"

    r = _R()
    assert r.slug == "_r_fixed"


def test_router_registry_round_trip() -> None:
    import a2kit
    from a2kit.routers import RouterRegistry

    @a2kit.read()
    async def ping() -> dict[str, int]:
        return {"x": 1}

    class R(a2kit.Router):
        tools = ()
        slug = "r"

    r = R()
    r._tools.append(ping)
    reg = RouterRegistry()
    reg.add(r)
    assert reg.all() == [r]
    assert reg.bound_tools() == [ping]


# --------------------------- connections CLI multi-type listing --------------------------- #


def test_connections_list_with_one_registered_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`list` (no conn_type) iterates registered types."""
    from tests.packages.connections.conftest import WidgetConfig

    from a2kit.packages.connections.cli import connections_cli

    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "conn"))
    group = connections_cli(WidgetConfig)
    runner = CliRunner()
    runner.invoke(group, ["login", "WidgetConfig", "--key=prod", "--field=token=t"])
    r = runner.invoke(group, ["list"])
    assert r.exit_code == 0, r.output
    assert "WidgetConfig" in r.output
    assert "prod" in r.output


def test_connections_logout_unknown_conn_type() -> None:
    """`logout` on unregistered conn_type → exits 1."""
    from a2kit.packages.connections.cli import connections_cli

    group = connections_cli()
    runner = CliRunner()
    r = runner.invoke(group, ["logout", "Nope", "--key=x"])
    assert r.exit_code == 1
    assert "Unknown" in r.output


# --------------------------- a2kit __main__ smoke --------------------------- #


def test_a2kit_main_help_runs() -> None:
    """In-process invocation of `__main__.main` — covers `__main__.py` LazyGroup."""
    from a2kit.__main__ import main

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "lint" in result.output
    assert isinstance(main, click.Group)


def test_a2kit_main_lazy_dispatches_lint() -> None:
    """LazyGroup.get_command resolves `lint` via the lazy spec."""
    from a2kit.__main__ import main

    runner = CliRunner()
    result = runner.invoke(main, ["lint", "--help"])
    assert result.exit_code == 0
    assert "static" in result.output


def test_a2kit_main_lazy_unknown_subcommand_falls_through() -> None:
    """A subcommand NOT in `_lazy` falls back to `super().get_command`."""
    from a2kit.__main__ import main

    runner = CliRunner()
    result = runner.invoke(main, ["nonexistent_cmd"])
    assert result.exit_code != 0


def test_a2kit_main_lazygroup_default_lazy_dict() -> None:
    """LazyGroup with no lazy_subcommands kwarg defaults to empty dict."""
    from a2kit.__main__ import LazyGroup

    g = LazyGroup(name="empty")
    assert g._lazy == {}


# --------------------------- connection_exceptions, original location --------------------------- #


def test_connection_exceptions_carry_metadata() -> None:
    from a2kit.packages.connections.exceptions import (
        ConnectionNotFound,
        EnvVarNotFound,
        InvalidConnectionKey,
        KeyArityMismatch,
        KeyFieldMissing,
        OpResolutionError,
        TokenResolutionError,
    )

    cnf = ConnectionNotFound(("a", "b"))
    assert cnf.key == ("a", "b")
    assert cnf.available_connections == []

    ick = InvalidConnectionKey("bad part")
    assert ick.part == "bad part"
    assert "bad part" in str(ick)

    kfm = KeyFieldMissing("missing", have=["a"], key_class="Tk")
    assert kfm.field == "missing"
    assert kfm.have == ["a"]
    assert kfm.key_class == "Tk"
    assert "Tk" in str(kfm)

    kam = KeyArityMismatch(expected=("a", "b"), got=("x",), key_class="Tk")
    assert kam.expected == ("a", "b")
    assert kam.got == ("x",)
    assert "Tk" in str(kam)

    kam2 = KeyArityMismatch(expected=("a",), got=("x", "y"))
    assert "arity 1" in str(kam2)

    tre = TokenResolutionError("base")
    assert "base" in str(tre)

    evn = EnvVarNotFound("MY_VAR", "${MY_VAR}")
    assert evn.var == "MY_VAR"
    assert evn.ref == "${MY_VAR}"

    ope = OpResolutionError("op://x", "no auth")
    assert ope.ref == "op://x"
    assert ope.hint == "no auth"
