"""Build the top-level CLI for an :class:`a2kit.App` (Typer-driven).

Cold-start invariant: ``import a2kit`` must NOT trigger ``import typer``
or ``import fastmcp``. Typer is imported at the top of this module, so
the invariant is upheld by ``a2kit.__init__`` not loading this module
eagerly (``a2kit.run`` lazy-imports it). ``fastmcp`` is imported inside
the ``serve`` callback body so ``<app> --help`` never pays for it.

Composition: top-level ``--help`` lists one entry per Router plus the
``schema`` / ``serve`` / (optional) ``health`` subcommands. The user runs
``<app> <router-slug> --help`` to see that router's tools and
``<app> <router-slug> <tool> --help`` to see the tool's options.

Body-model UX: a tool param typed as ``body: SomeBaseModel`` is exposed
on the CLI as a single ``--body <json>`` flag and decoded via
``SomeBaseModel.model_validate_json``. MCP keeps the structured form
unchanged. See ``docs/adr/0001-typer-cli.md``.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable  # noqa: TC003 — runtime-used in signatures
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, cast, get_type_hints

import typer

from a2kit.packages.cli._serve import register_code, register_serve

if TYPE_CHECKING:
    import click
    from pydantic import BaseModel

    from a2kit.app import App
    from a2kit.routers import Router


class _CliFormat(StrEnum):
    auto = "auto"
    json = "json"
    tsv = "tsv"
    page_tsv = "page-tsv"


_MD_INLINE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("**", ""),
    ("__", ""),
    ("`", ""),
)


def _strip_md(text: str) -> str:
    """Coarse markdown stripper for terminal rendering.

    Removes inline emphasis markers (``**bold**`` → ``bold``, ``*italic*`` →
    ``italic``, ``` `code` ``` → ``code``); rewrites ``[text](url)`` links to
    ``text (url)``. Block constructs (headers, lists, code fences) pass
    through unchanged — terminals render them readable enough.
    """
    out = text
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", out)
    for marker, repl in _MD_INLINE_PATTERNS:
        out = out.replace(marker, repl)
    out = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", out)
    out = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", out)
    return out


def _docstring_to_help(fn: Callable[..., Any]) -> tuple[str, str]:
    """Return ``(short_help, long_help)`` for a tool function's docstring."""
    raw = inspect.getdoc(fn)
    if not raw:
        return "", ""
    lines = raw.splitlines()
    short = next((line.strip() for line in lines if line.strip()), "")
    long_help = _strip_md(raw)
    return short, long_help


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


def _is_basemodel(ann: Any) -> type[BaseModel] | None:
    """Return the BaseModel subclass if ``ann`` (or its inner Annotated/Optional) is one."""
    import types
    from typing import Union, get_args, get_origin

    from pydantic import BaseModel

    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return ann
    if hasattr(ann, "__metadata__"):
        inner = get_args(ann)[0]
        return _is_basemodel(inner)
    origin = get_origin(ann)
    if origin is Union or origin is types.UnionType:
        for a in get_args(ann):
            if a is type(None):
                continue
            found = _is_basemodel(a)
            if found is not None:
                return found
    return None


def _strip_optional(ann: Any) -> Any:
    """If ``ann`` is ``T | None`` or ``Optional[T]``, return ``T``; else unchanged."""
    import types
    from typing import Union, get_args, get_origin

    origin = get_origin(ann)
    if origin is Union or origin is types.UnionType:
        args = [a for a in get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return ann


def _needs_json_decode(ann: Any) -> bool:
    """Return True if ``ann`` is a non-primitive (list/dict/tuple/set/...) wire type.

    Primitives (str/int/float/bool) and BaseModel parameters are handled
    elsewhere; everything else is exposed as a single ``--flag '<json>'``
    string and JSON-decoded inside the callback.

    Walks through nested ``Annotated[...]`` and ``Optional[...]`` layers to a
    fixed point — pathological wrappings like
    ``Optional[Annotated[Optional[list[int]], ...]]`` still reach the inner
    container type.
    """
    from typing import get_args as _ga

    inner = ann
    for _ in range(8):  # bounded; pathological depth is rejected by Python's typing layer anyway
        next_inner = _strip_optional(inner)
        if hasattr(next_inner, "__metadata__"):
            next_inner = _ga(next_inner)[0]
        if next_inner is inner:
            break
        inner = next_inner
    if inner is inspect.Parameter.empty or inner is Any:
        return False
    return inner not in (bool, int, float, str)


def _build_tool_callback(fn: Callable[..., Any], app: App, router: Router | None) -> Callable[..., None]:
    """Synthesize a Typer-compatible callback for tool ``fn``.

    The returned callable carries a ``__signature__`` and ``__annotations__``
    derived from ``fn``'s wire params, with FieldInfo descriptions rewritten
    to ``typer.Option(help=...)``. Built-in options ``--format``, ``--schema``,
    and (when applicable) ``--connection`` are added.

    The callback handles: schema dump, JSON body decode, format routing,
    LDD enable/disable, enricher chain, and exception → exit-code mapping.
    """
    import typer

    from a2kit.metadata import get_meta
    from a2kit.packages.cli._field_to_typer import field_to_typer_annotation
    from a2kit.packages.cli.runtime import invoke_tool_sync
    from a2kit.packages.formatter import FormatHint, format_response
    from a2kit.packages.formatter.inference import infer_format_hint
    from a2kit.signature import wire_input_params

    meta = get_meta(fn)
    container = app.container()
    params, wire_scopes_needed = wire_input_params(fn, container)
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

    body_model_params: dict[str, type[BaseModel]] = {}
    json_decode_params: set[str] = set()
    required_names: set[str] = set()
    sig_params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {}

    for name, param in params.items():
        ann = annotated_hints.get(name, param.annotation)
        body_cls = _is_basemodel(_strip_optional(ann))
        has_default = param.default is not inspect.Parameter.empty
        # All wire params are optional at Typer's parse layer so the ``--schema``
        # flag can short-circuit before required-check. The callback enforces
        # required-ness against ``required_names``.
        cli_default = param.default if has_default else None
        if not has_default:
            required_names.add(name)

        if body_cls is not None:
            body_model_params[name] = body_cls
            new_ann = Annotated[
                str | None,
                typer.Option(help=f"JSON object decoded into {body_cls.__name__}."),
            ]
            sig_params.append(inspect.Parameter(name, kind=inspect.Parameter.KEYWORD_ONLY, default=cli_default, annotation=new_ann))
            annotations[name] = new_ann
            continue

        if _needs_json_decode(ann):
            json_decode_params.add(name)
            new_ann = Annotated[str | None, typer.Option(help="JSON value.")]
            sig_params.append(inspect.Parameter(name, kind=inspect.Parameter.KEYWORD_ONLY, default=cli_default, annotation=new_ann))
            annotations[name] = new_ann
            continue

        new_ann = field_to_typer_annotation(ann)
        sig_params.append(inspect.Parameter(name, kind=inspect.Parameter.KEYWORD_ONLY, default=cli_default, annotation=new_ann))
        annotations[name] = new_ann

    if needs_connection and "connection" not in params:
        conn_ann = Annotated[str | None, typer.Option(help="Connection name (single key, or comma-separated).")]
        sig_params.append(inspect.Parameter("connection", kind=inspect.Parameter.KEYWORD_ONLY, default=None, annotation=conn_ann))
        annotations["connection"] = conn_ann
        required_names.add("connection")

    fmt_ann = Annotated[_CliFormat, typer.Option(help="Output format. 'auto' uses type-driven routing.")]
    sig_params.append(inspect.Parameter("format", kind=inspect.Parameter.KEYWORD_ONLY, default=_CliFormat.auto, annotation=fmt_ann))
    annotations["format"] = fmt_ann

    schema_ann = Annotated[bool, typer.Option("--schema", hidden=True, help="Print this tool's schema and exit.")]
    sig_params.append(inspect.Parameter("schema", kind=inspect.Parameter.KEYWORD_ONLY, default=False, annotation=schema_ann))
    annotations["schema"] = schema_ann

    wrapped_fn = _wrap_with_enricher(fn, router)

    def callback(**kwargs: Any) -> None:
        import click as _click

        fmt_enum: _CliFormat = kwargs.pop("format", _CliFormat.auto)
        fmt: str = descriptor_hint if fmt_enum == _CliFormat.auto else fmt_enum.value
        if kwargs.pop("schema", False):
            from a2kit.schema import compute_schema

            schema = compute_schema(fn, container=app.container())
            schema_fmt = "json" if fmt in ("tsv", "page-tsv") else fmt
            typer.echo(format_response(schema, format_hint=cast("FormatHint", schema_fmt)).data)
            return

        missing = [n for n in required_names if kwargs.get(n) is None]
        if missing:
            opts = ", ".join(f"--{n.replace('_', '-')}" for n in missing)
            raise typer.BadParameter(f"Missing required option(s): {opts}")

        call_kwargs: dict[str, Any] = {}
        for pname, param in params.items():
            value = kwargs.get(pname)
            if value is None and param.default is not inspect.Parameter.empty:
                continue
            if pname in body_model_params and isinstance(value, str):
                try:
                    value = body_model_params[pname].model_validate_json(value)
                except Exception as exc:
                    dashed = pname.replace("_", "-")
                    msg = f"--{dashed} expects a JSON object for {body_model_params[pname].__name__}: {exc}"
                    raise typer.BadParameter(msg) from exc
            elif pname in json_decode_params and isinstance(value, str):
                import json as _json

                try:
                    value = _json.loads(value)
                except _json.JSONDecodeError as exc:
                    dashed = pname.replace("_", "-")
                    msg = f"--{dashed} expects a JSON value: {exc}"
                    raise typer.BadParameter(msg) from exc
            call_kwargs[pname] = value

        if needs_connection and kwargs.get("connection") is not None:
            call_kwargs["connection"] = kwargs["connection"]

        ctx_param = meta.context_param_name if meta is not None else None
        report_type = meta.extras.report_type if meta is not None else None

        root_ctx = _click.get_current_context().find_root()
        store = root_ctx.obj if isinstance(root_ctx.obj, dict) else {}
        no_reports = bool(store.get("no_reports", False))
        no_events = bool(store.get("no_events", False))
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
        except _click.ClickException:
            raise
        except Exception as exc:
            typer.echo(f"error: {exc}", err=True)
            if getattr(app, "debug", False):
                import traceback

                typer.echo(traceback.format_exc(), err=True)
            raise typer.Exit(1) from exc
        typer.echo(data)

    short_help, long_help = _docstring_to_help(fn)
    callback.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    callback.__annotations__ = annotations
    callback.__doc__ = long_help or None
    callback.__name__ = meta.tool_name if meta is not None else getattr(fn, "__name__", "tool")
    callback._a2kit_short_help = short_help  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # noqa: SLF001
    return callback


def _register_router(typer_app: Any, router: Router, app: App) -> None:
    """Add a sub-Typer for ``router`` to ``typer_app``."""
    import typer

    from a2kit.metadata import get_meta

    sub = typer.Typer(
        name=router.slug,
        help=f"Tools in router {router.slug!r}.",
        no_args_is_help=True,
        pretty_exceptions_enable=False,
    )
    for fn in router.bound_tools():
        meta = get_meta(fn)
        hidden = False
        if meta is not None:
            visibility = meta.extras.visibility or "all"
            # All three tiers ("hidden", "cli", "all") mount on CLI.
            # Only "hidden" omits from --help listing.
            hidden = visibility == "hidden"
        cb = _build_tool_callback(fn, app, router=router)
        tool_name = meta.tool_name if meta is not None else getattr(fn, "__name__", "tool")
        short = getattr(cb, "_a2kit_short_help", "") or None
        sub.command(name=tool_name, help=cb.__doc__, short_help=short, hidden=hidden)(cb)
    typer_app.add_typer(sub)


def _register_schema(typer_app: Any, app: App) -> None:
    """Register the ``schema [tool]`` subcommand."""
    import json as _json

    import typer

    from a2kit.metadata import get_meta
    from a2kit.packages.formatter import format_response, truncate

    def schema_cmd(
        tool_name: Annotated[str | None, typer.Argument(help="Tool name; omit to dump all.")] = None,
        format: Annotated[  # noqa: A002
            _CliFormat, typer.Option("--format", help="Output format.")
        ] = _CliFormat.auto,
        jsonl: Annotated[bool, typer.Option("--jsonl", help="One JSON schema per line (--format=json).")] = False,
    ) -> None:
        """Print tool schemas. Default format is auto (JSON unless type-driven routing picks otherwise)."""
        from a2kit.schema import compute_schema

        container = app.container()
        schemas: dict[str, dict[str, Any]] = {}
        for desc in app.tools():
            fn = desc.fn
            meta = get_meta(fn)
            name = meta.tool_name if meta is not None else getattr(fn, "__name__", "tool")
            schemas[name] = compute_schema(fn, container)

        if tool_name is not None:
            result: Any = schemas.get(tool_name)
            if result is None:
                msg = f"Unknown tool: {tool_name!r}. Known: {sorted(schemas)}"
                raise typer.BadParameter(msg)
        else:
            result = schemas

        fmt = format.value

        if jsonl:
            if fmt != "json":
                raise typer.BadParameter("--jsonl requires --format=json")
            if tool_name is not None:
                typer.echo(truncate(_json.dumps(result, separators=(",", ":"), default=str)))
                return
            for s in result.values():
                typer.echo(truncate(_json.dumps(s, separators=(",", ":"), default=str)))
            return

        response = format_response(result, format_hint=fmt)
        typer.echo(truncate(response.data))

    typer_app.command(name="schema")(schema_cmd)


def _register_health(typer_app: Any, app: App) -> None:
    """Register the ``health`` shorthand for ``_meta.health``.

    Runs the aggregated probe by calling
    :func:`a2kit.packages.health.run_checks` inside the App's async-CM
    lifecycle (``async with app:``). The test-client (and its
    ``pytest`` import) are NOT imported by this path, so
    ``<app> health`` works on fresh non-dev installs.
    """
    import asyncio
    import json as _json

    import typer

    from a2kit.packages.health import app_version, run_checks

    def health_cmd() -> None:
        """Run aggregated health probe; exits non-zero on degraded."""

        async def _run() -> dict[str, Any]:
            async with app:
                registry = app._health  # noqa: SLF001 -- App-scoped health registry
                resolver = app._resolver  # noqa: SLF001 -- framework resolver seam
                return await run_checks(registry, resolver, version=app_version(app))

        result = asyncio.run(_run())
        typer.echo(_json.dumps(result, indent=2))
        if result.get("status") != "ok":
            raise typer.Exit(1)

    typer_app.command(name="health")(health_cmd)


def build_full_cli(app: App) -> click.Command:
    """Build the top-level CLI for ``app`` as a ``click.Command`` (Typer-backed).

    Top-level commands:
      - one subgroup per Router (slug-named)
      - any user-registered ``app.add_cli(...)`` commands (Click commands)
      - ``schema`` (eager, closes over app)
      - ``serve`` (LAZY — fastmcp imported only inside the callback body)
      - ``code`` (LAZY — sandbox runtime imported only inside the callback)
      - ``health`` (only when ``app._health.enabled``)

    Top-level flags ``--no-reports`` / ``--no-events`` disable LDD channels
    for the invocation; they override ``App.set_ldd(...)`` and the
    ``A2KIT_LDD`` env var.
    """
    import typer

    routers = list(app.routers())
    router_help_lines = [f"  {r.slug}  (run `{app.name} {r.slug} --help` for tools)" for r in routers]
    help_text = (app.name or "a2kit") + " — agent toolkit CLI."
    if router_help_lines:
        help_text += "\n\nRouters:\n" + "\n".join(router_help_lines)

    main = typer.Typer(
        name=app.name or "a2kit",
        help=help_text,
        no_args_is_help=True,
        pretty_exceptions_enable=False,
        rich_markup_mode=None,
        add_completion=False,
    )

    @main.callback(invoke_without_command=True)
    def _root(
        ctx: typer.Context,
        no_reports: Annotated[bool, typer.Option("--no-reports", help="Disable ctx.report emission.")] = False,
        no_events: Annotated[bool, typer.Option("--no-events", help="Disable ctx.event emission.")] = False,
    ) -> None:
        # Stash on ctx.obj so tool callbacks read from a stable contract,
        # not from typer-callback-name-shaped ctx.params keys.
        store = ctx.ensure_object(dict)
        store["no_reports"] = no_reports
        store["no_events"] = no_events

    for router in routers:
        _register_router(main, router, app)

    _register_schema(main, app)
    register_serve(main, app)
    register_code(main, app)
    if getattr(app, "_health", None) is not None and app._health.enabled:  # noqa: SLF001
        _register_health(main, app)

    command = typer.main.get_command(main)
    extras = list(app.cli_extras())
    if extras:
        # cli_extras are click.Command objects; we need a Group to attach them.
        # Typer always returns a Group when commands are registered (schema/serve
        # are unconditional, so this is invariant for our build). Guard anyway.
        import click as _click

        if not isinstance(command, _click.Group):
            msg = "build_full_cli: root Typer command is not a click.Group; cannot attach cli_extras"
            raise TypeError(msg)
        for cmd in extras:
            command.add_command(cmd)
    return command


__all__ = ["build_full_cli"]
