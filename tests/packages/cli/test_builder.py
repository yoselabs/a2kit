"""build_full_cli: progressive disclosure, lazy serve, eager subgroups."""

from __future__ import annotations

import click
from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli


def test_returns_click_command(app):
    cli = build_full_cli(app)
    assert isinstance(cli, click.Command)
    # Typer-backed: the root is a click.Group (typer.main.get_command(main)).
    assert isinstance(cli, click.Group)


def test_top_level_help_lists_routers_and_subgroups(app):
    cli = build_full_cli(app)
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    # Router subgroup, schema, and lazy serve. The `connections` subgroup
    # is plugin-contributed (not present unless `Connections()` is registered).
    assert "tasks" in result.output
    assert "schema" in result.output
    assert "serve" in result.output


def test_connections_subgroup_only_when_added(tasks_router):
    """`<app> connections ...` appears iff `app.add_cli(connections_cli(...))` is wired."""
    from tests.packages.connections.conftest import WidgetConfig

    from a2kit.packages.connections import connections_cli

    # Without add_cli: no connections subgroup.
    bare = a2kit.App("bare").add_router(tasks_router)
    cli = build_full_cli(bare)
    out = CliRunner().invoke(cli, ["--help"]).output
    assert "connections" not in out

    # With add_cli: connections subgroup present.
    with_cli = a2kit.App("withcli").add_router(tasks_router).add_cli(connections_cli(WidgetConfig))
    cli2 = build_full_cli(with_cli)
    out2 = CliRunner().invoke(cli2, ["--help"]).output
    assert "connections" in out2


def test_router_subgroup_lists_its_tools(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "--help"])
    assert result.exit_code == 0
    assert "get_task" in result.output
    assert "list_tasks" in result.output
    assert "create_task" in result.output


def test_tool_help_renders_options(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "get_task", "--help"])
    assert result.exit_code == 0
    assert "--task-id" in result.output
    assert "--format" in result.output


def test_progressive_disclosure_hint_in_help(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    # Some hint that running `<app> <slug>` dives deeper.
    assert "tasks" in result.output


def test_lazy_serve_does_not_load_fastmcp_at_build_time():
    import subprocess
    import sys as _sys

    # Run in a subprocess so we don't pollute the test process's module cache —
    # `del sys.modules['fastmcp']` invalidates the FastMCP class identity for
    # other tests in the suite (isinstance() fails after re-import).
    script = (
        "import sys\n"
        "import a2kit\n"
        "from a2kit.packages.cli.builder import build_full_cli\n"
        "from click.testing import CliRunner\n"
        "class T(a2kit.Router):\n"
        "    slug = 't'\n"
        "    @a2kit.read('list_tasks')\n"
        "    def list_tasks(self, *, limit: int = 10) -> dict:\n"
        "        return {}\n"
        "    tools = (list_tasks,)\n"
        "app = a2kit.App('demo').add_router(T())\n"
        "CliRunner().invoke(build_full_cli(app), ['--help'])\n"
        "print('fastmcp' in sys.modules)\n"
    )
    out = subprocess.check_output([_sys.executable, "-c", script], text=True)
    assert out.strip() == "False", f"build_full_cli must not eagerly load fastmcp; got: {out!r}"


def test_unknown_router_returns_nonzero(app):
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["does_not_exist"])
    assert result.exit_code != 0


def test_schema_command_sees_app(app):
    """schema command closes over the active App via the build_full_cli factory."""
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["schema", "get_task", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert "get_task" in result.output


def test_empty_app_still_builds():
    empty = a2kit.App("empty")
    cli = build_full_cli(empty)
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0


# --- Nullable primitive option synthesis ----------------------------------- #


def test_optional_int_maps_to_integer_click_option():
    import a2kit
    from a2kit.packages.cli.builder import build_full_cli

    class Probe(a2kit.Router):
        slug = "probe"
        name = "probe"

        @a2kit.read("get")
        def get(self, *, project_id: int | None = None) -> dict:
            return {"project_id": project_id}
        tools = (get,)

    app = a2kit.App("probe").add_router(Probe())
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["probe", "get", "--help"])
    assert result.exit_code == 0
    assert "--project-id INTEGER" in result.output


def test_optional_str_invokes_with_string_value():
    import a2kit
    from a2kit.packages.cli.builder import build_full_cli

    seen: dict = {}

    class Probe(a2kit.Router):
        slug = "probe"
        name = "probe"

        @a2kit.read("get")
        def get(self, *, query: str | None = None) -> dict:
            seen["query"] = query
            return {"query": query}
        tools = (get,)

    app = a2kit.App("probe").add_router(Probe())
    result = CliRunner().invoke(build_full_cli(app), ["probe", "get", "--query", "hello"])
    assert result.exit_code == 0
    assert seen["query"] == "hello"


def test_optional_bool_maps_to_flag():
    import a2kit
    from a2kit.packages.cli.builder import build_full_cli

    class Probe(a2kit.Router):
        slug = "probe"
        name = "probe"

        @a2kit.read("get")
        def get(self, *, verbose: bool | None = None) -> dict:
            return {"verbose": verbose}
        tools = (get,)

    app = a2kit.App("probe").add_router(Probe())
    result = CliRunner().invoke(build_full_cli(app), ["probe", "get", "--help"])
    assert result.exit_code == 0
    # Flag form: --verbose/--no-verbose
    assert "--verbose" in result.output and "--no-verbose" in result.output


def test_nonprimitive_nullable_still_json_decodes():
    """Regression guard: list[int] | None stays JSON-decode mode."""
    import a2kit
    from a2kit.packages.cli.builder import build_full_cli

    seen: dict = {}

    class Probe(a2kit.Router):
        slug = "probe"
        name = "probe"

        @a2kit.read("get")
        def get(self, *, ids: list[int] | None = None) -> dict:
            seen["ids"] = ids
            return {"ids": ids}
        tools = (get,)

    app = a2kit.App("probe").add_router(Probe())
    result = CliRunner().invoke(build_full_cli(app), ["probe", "get", "--ids", "[1,2,3]"])
    assert result.exit_code == 0, result.output
    assert seen["ids"] == [1, 2, 3]
