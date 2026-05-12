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
from a2kit.signature import wire_input_params

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


_MD_INLINE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("**", ""),  # bold
    ("__", ""),
    ("`", ""),  # inline code
)


def _strip_md(text: str) -> str:
    """Coarse markdown stripper for terminal rendering.

    Removes inline emphasis markers (``**bold**`` → ``bold``, ``*italic*`` →
    ``italic``, ``` `code` ``` → ``code``); rewrites ``[text](url)`` links to
    ``text (url)``. Block constructs (headers, lists, code fences) pass
    through unchanged — terminals render them readable enough.
    """
    import re

    out = text
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", out)
    for marker, repl in _MD_INLINE_PATTERNS:
        out = out.replace(marker, repl)
    # Single-asterisk italics: replace pairs but leave bare * (e.g. lists) alone.
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", out)
    out = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", out)
    return out


def _docstring_to_help(fn: Callable[..., Any]) -> tuple[str, str]:
    """Return ``(short_help, long_help)`` for a tool function's docstring.

    Short help is the first non-empty line of the dedented docstring.
    Long help is the full PEP-257-dedented body with markdown stripped for
    terminal rendering.
    """
    import inspect as _inspect

    raw = _inspect.getdoc(fn)
    if not raw:
        return "", ""
    lines = raw.splitlines()
    short = next((line.strip() for line in lines if line.strip()), "")
    long_help = _strip_md(raw)
    return short, long_help


def _option_name(param_name: str) -> str:
    return "--" + param_name.replace("_", "-")


def _wrap_with_enricher(fn: Callable[..., Any], router: Router | None = None) -> Callable[..., Any]:
    """Wrap ``fn`` with the router's enricher chain (class list + ``enrich`` method)."""
    if router is None:
        return fn
    enrichers = list(getattr(type(router), "enrichers", None) or ())
    enrich_method = getattr(router, "enrich", None)
    if not enrichers and not callable(enrich_method):
        return fn

    import functools

    @functools.wraps(fn)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:
            if callable(enrich_method):
                msg = enrich_method(exc)
                if msg is not None:
                    raise type(exc)(msg) from exc
            for enricher in enrichers:
                msg = enricher(exc)
                if msg is not None:
                    raise type(exc)(msg) from exc
            raise

    return _wrapped


def _make_tool_command(fn: Callable[..., Any], app: App, router: Router | None = None) -> click.Command:
    from a2kit.packages.formatter.inference import infer_format_hint

    meta = get_meta(fn)
    tool_name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
    short_help, long_help = _docstring_to_help(fn)

    container = app.container()
    params, wire_scopes_needed = wire_input_params(fn, container)
    # Today only "connection" is registered as a wire scope; if more scope
    # names get registered in the future, this is the site that maps each
    # to a synthesized CLI option.
    needs_connection = "connection" in wire_scopes_needed
    try:
        resolved_hints = get_type_hints(fn)
    except Exception:  # noqa: BLE001
        resolved_hints = {}
    try:
        annotated_hints = get_type_hints(fn, include_extras=True)
    except Exception:  # noqa: BLE001
        annotated_hints = {}

    descriptor_hint = infer_format_hint(resolved_hints.get("return"))
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
        from a2kit._field_introspect import description_of

        param_desc = description_of(annotated_hints.get(name))
        if param_desc:
            opt_kwargs["help"] = param_desc
        click_params.append(click.Option([opt_name, name], **opt_kwargs))

    if needs_connection and "connection" not in params:
        click_params.append(
            click.Option(
                ["--connection", "connection"],
                type=click.STRING,
                required=True,
                show_default=False,
                help="Connection name (single key, or comma-separated for multi-field keys).",
            )
        )

    click_params.append(
        click.Option(
            ["--format", "fmt"],
            type=click.Choice(["auto", "json", "tsv", "page-tsv"]),
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

    wrapped_fn = _wrap_with_enricher(fn, router)

    def callback(**kwargs: Any) -> None:
        fmt = kwargs.pop("fmt", "auto")
        # Type-driven routing: "auto" resolves to the descriptor's
        # pre-computed hint at command-build time.
        if fmt == "auto":
            fmt = descriptor_hint
        schema_flag = kwargs.pop("schema", False)
        if schema_flag:
            schema = compute_schema(fn, container=app.container())
            # Schemas are dicts; keep them on the JSON path regardless of the
            # tool's descriptor hint.
            schema_fmt = "json" if fmt in ("tsv", "page-tsv") else fmt
            click.echo(format_response(schema, format_hint=cast("FormatHint", schema_fmt)).data)
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

        # Auto-added wire ``connection`` (when injectable graph reaches it
        # but the tool method itself doesn't declare ``connection``) is
        # kept on call_kwargs so the dispatch hook can use it for chain
        # resolution. The hook strips it before calling fn if fn doesn't
        # declare it.
        if needs_connection and "connection" in kwargs and kwargs["connection"] is not None:
            call_kwargs["connection"] = kwargs["connection"]

        ctx_param = meta.context_param_name if meta is not None else None
        report_type = meta.extras.report_type if meta is not None else None

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
                dispatch_hook=app.dispatch_hook(),
                app=app,
            )
        except click.ClickException:
            raise
        except Exception as exc:
            click.echo(f"error: {exc}", err=True)
            if getattr(app, "debug", False):
                import traceback

                click.echo(traceback.format_exc(), err=True)
            raise click.exceptions.Exit(1) from exc
        click.echo(data)

    return click.Command(
        name=tool_name,
        params=click_params,
        callback=callback,
        help=long_help,
        short_help=short_help,
    )


def _router_group(router: Router, app: App) -> click.Group:
    """Build a Click group containing one subcommand per tool on ``router``."""
    from a2kit.metadata import get_meta
    from a2kit.surface import Surface

    group = click.Group(
        name=router.slug,
        help=f"Tools in router {router.slug!r}.",
    )
    for fn in router.bound_tools():
        meta = get_meta(fn)
        if meta is not None:
            tool_surfaces = meta.extras.surfaces or Surface.ALL
            if Surface.CLI not in tool_surfaces:
                continue
        group.add_command(_make_tool_command(fn, app, router=router))
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
    # `<app> health` shorthand for `_meta.health`. Only registered when the
    # health probe is enabled — keeps the surface clean for apps that didn't
    # opt in.
    if getattr(app, "_health", None) is not None and app._health.enabled:  # noqa: SLF001
        group.add_command(_build_health_command(app))
    return group


def _build_health_command(app: App) -> click.Command:
    """``<app> health`` — invoke ``_meta.health`` and exit non-zero on degraded."""
    import json

    from a2kit.packages.health import HEALTH_TOOL_NAME

    @click.command(name="health", help="Run aggregated health probe; exits non-zero on degraded.")
    def _health_cmd() -> None:
        from a2kit.packages.testing.client import client as _client

        async def _run() -> dict[str, Any]:
            async with _client(app) as c:
                result = await c.invoke(HEALTH_TOOL_NAME)
                return result if isinstance(result, dict) else {"status": "unknown"}

        import asyncio

        result = asyncio.run(_run())
        click.echo(json.dumps(result, indent=2))
        if result.get("status") != "ok":
            raise click.exceptions.Exit(1)

    return _health_cmd


__all__ = ["LazyGroup", "build_full_cli"]
