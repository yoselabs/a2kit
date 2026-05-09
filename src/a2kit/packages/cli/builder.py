"""Build the top-level Click group for an :class:`a2kit.App`.

Cold-start invariant: importing this module must NOT trigger ``fastmcp``.
The ``serve`` subcommand is registered as a deferred factory; its body
imports fastmcp only when the user actually runs ``<app> serve``.

Composition: top-level ``--help`` shows one entry per Router. The user
runs ``<app> <router-slug> --help`` to see that router's tools, and
``<app> <router-slug> <tool> --help`` to see the tool's options.

App propagation: handlers close over ``app`` directly via the factories
constructed in :func:`build_full_cli`. There is no ContextVar and no
post-construction monkey-patch.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast, get_type_hints

import click

from a2kit.metadata import get_meta
from a2kit.packages.cli.runtime import invoke_tool_sync
from a2kit.packages.cli.schemas import build_schema_command, compute_schema
from a2kit.packages.formatter import FormatHint, format_response
from a2kit.signature import user_input_params

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.routers import Router


CommandFactory = Callable[[], click.Command]


class LazyGroup(click.Group):
    """Click group with subcommands materialized on demand from factories.

    ``lazy_subcommands`` maps subcommand name → ``Callable[[], click.Command]``.
    The factory is called only when the subcommand is resolved, so the
    factory body (which may perform expensive imports such as fastmcp) does
    not execute during top-level ``--help`` rendering.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, CommandFactory] | None = None,
        lazy_short_help: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._lazy: dict[str, CommandFactory] = lazy_subcommands or {}
        self._lazy_short_help: dict[str, str] = lazy_short_help or {}
        self._lazy_cache: dict[str, click.Command] = {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self._lazy})

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._lazy:
            cached = self._lazy_cache.get(cmd_name)
            if cached is None:
                cached = self._lazy[cmd_name]()
                self._lazy_cache[cmd_name] = cached
            return cached
        return super().get_command(ctx, cmd_name)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # Render lazy subcommands with their static short_help so `--help` does NOT
        # call the factory — preserves the cold-start invariant for `serve`.
        rows: list[tuple[str, str]] = []
        for name in sorted(set(super().list_commands(ctx))):
            cmd = super().get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            rows.append((name, cmd.get_short_help_str(limit=80) or ""))
        for name in sorted(self._lazy):
            rows.append((name, self._lazy_short_help.get(name, "")))
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


def _strip_optional(annotation: Any) -> Any:
    import types
    import typing

    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _click_type_for(annotation: Any) -> tuple[Any, bool]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return click.STRING, False
    inner = _strip_optional(annotation)
    if inner is bool:
        return bool, False
    if inner in (int, float, str):
        return inner, False
    return click.STRING, True


def _option_name(param_name: str) -> str:
    return "--" + param_name.replace("_", "-")


def _wrap_with_enricher(fn: Callable[..., Any]) -> Callable[..., Any]:
    """If the tool's meta carries an ``a2kit.enricher`` extra key, wrap fn with it."""
    meta = get_meta(fn)
    if meta is None:
        return fn
    enricher = meta.extra.get("a2kit.enricher")
    if enricher is None:
        return fn
    from a2kit.packages.enrichers import wrap

    return wrap(fn, enricher)


def _make_tool_command(fn: Callable[..., Any], app: App) -> click.Command:
    meta = get_meta(fn)
    tool_name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
    description = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""

    params = user_input_params(fn)
    try:
        resolved_hints = get_type_hints(fn)
    except Exception:  # noqa: BLE001
        resolved_hints = {}
    required_names: set[str] = set()
    json_decode_params: set[str] = set()
    click_params: list[click.Parameter] = []

    for name, param in params.items():
        opt_name = _option_name(name)
        ann = resolved_hints.get(name, param.annotation)
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None
        if not has_default:
            required_names.add(name)

        inner_ann = _strip_optional(ann)
        if inner_ann is bool:
            dashed = name.replace("_", "-")
            opt = click.Option(
                [f"--{dashed}/--no-{dashed}"],
                default=default if has_default else False,
                required=False,
            )
            opt.name = name
            click_params.append(opt)
            continue

        click_type, complex_json = _click_type_for(ann)
        if complex_json:
            json_decode_params.add(name)
        opt_kwargs: dict[str, Any] = {
            "type": click_type,
            "required": False,
            "show_default": has_default,
        }
        if has_default:
            opt_kwargs["default"] = default
        click_params.append(click.Option([opt_name, name], **opt_kwargs))

    click_params.append(
        click.Option(
            ["--format", "fmt"],
            type=click.Choice(["auto", "toon", "json"]),
            default="auto",
            show_default=True,
        )
    )
    click_params.append(
        click.Option(
            ["--schema", "schema"],
            is_flag=True,
            hidden=True,
            default=False,
            help="Print this tool's schema and exit.",
        )
    )

    wrapped_fn = _wrap_with_enricher(fn)

    def callback(**kwargs: Any) -> None:
        fmt = kwargs.pop("fmt", "auto")
        schema_flag = kwargs.pop("schema", False)
        if schema_flag:
            schema = compute_schema(fn)
            click.echo(format_response(schema, format_hint=cast("FormatHint", fmt)).data)
            return

        missing = [n for n in required_names if kwargs.get(n) is None]
        if missing:
            opts = ", ".join(f"--{n.replace('_', '-')}" for n in missing)
            raise click.UsageError(f"Missing required option(s): {opts}")

        call_kwargs: dict[str, Any] = {}
        for name in params:
            value = kwargs.get(name)
            if value is None and params[name].default is not inspect.Parameter.empty:
                continue
            if name in json_decode_params and isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError as exc:
                    msg = f"--{name.replace('_', '-')} expects a JSON value: {exc}"
                    raise click.BadParameter(msg) from exc
            call_kwargs[name] = value

        ctx_param = meta.context_param_name if meta is not None else None
        report_type = meta.extra.get("a2kit.report_type") if meta is not None else None

        root_ctx = click.get_current_context().find_root()
        no_reports = bool(root_ctx.params.get("no_reports", False))
        no_events = bool(root_ctx.params.get("no_events", False))
        reports_enabled = app.ldd_reports and not no_reports
        events_enabled = app.ldd_events and not no_events

        try:
            data = invoke_tool_sync(
                wrapped_fn,
                call_kwargs,
                fmt=fmt,
                ctx_param_name=ctx_param,
                report_type=report_type,
                tool_name=meta.tool_name if meta is not None else None,
                reports_enabled=reports_enabled,
                events_enabled=events_enabled,
            )
        except click.ClickException:
            raise
        except Exception as exc:
            click.echo(f"error: {exc}", err=True)
            raise click.exceptions.Exit(1) from exc
        click.echo(data)

    return click.Command(
        name=tool_name,
        params=click_params,
        callback=callback,
        help=description,
        short_help=description,
    )


def _router_group(router: Router, app: App) -> click.Group:
    """Build a Click group containing one subcommand per tool on ``router``."""
    group = click.Group(
        name=router.slug,
        help=f"Tools in router {router.slug!r}.",
    )
    for fn in router.tools():
        group.add_command(_make_tool_command(fn, app))
    return group


def _build_serve_factory(app: App) -> CommandFactory:
    """Return a factory that materializes the ``serve`` Click command on demand."""

    def factory() -> click.Command:
        from a2kit.packages.mcp.cli import build_serve_command

        return build_serve_command(app)

    return factory


def build_full_cli(app: App) -> click.Command:
    """Build the top-level Click group for ``app``.

    Top-level commands:
      - one subgroup per Router (slug-named)
      - any user-registered ``app.add_cli(...)`` commands
      - ``schema`` (eager, closes over app)
      - ``serve`` (LAZY — only this triggers a fastmcp import)

    Top-level flags ``--no-reports`` / ``--no-events`` disable LDD channels
    for the invocation; they override ``App.set_ldd(...)`` and the
    ``A2KIT_LDD`` env var.
    """
    routers = list(app.routers())
    router_help_lines = [f"  {r.slug}  (run `{app.name} {r.slug} --help` for tools)" for r in routers]
    help_text = (app.name or "a2kit") + " — agent toolkit CLI."
    if router_help_lines:
        help_text += "\n\nRouters:\n" + "\n".join(router_help_lines)

    group = LazyGroup(
        name=app.name or "a2kit",
        help=help_text,
        lazy_subcommands={"serve": _build_serve_factory(app)},
        lazy_short_help={"serve": "Run as an MCP server (stdio or HTTP)."},
        params=[
            click.Option(
                ["--no-reports", "no_reports"],
                is_flag=True,
                default=False,
                help="Disable ctx.report emission for this invocation.",
            ),
            click.Option(
                ["--no-events", "no_events"],
                is_flag=True,
                default=False,
                help="Disable ctx.event emission for this invocation.",
            ),
        ],
    )

    for router in routers:
        group.add_command(_router_group(router, app))
    for cmd in app.cli_extras():
        group.add_command(cmd)
    group.add_command(build_schema_command(app))
    return group


__all__ = ["LazyGroup", "build_full_cli"]
