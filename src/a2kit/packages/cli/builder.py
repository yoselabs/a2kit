"""Build the top-level Click group for an :class:`a2kit.App`.

Cold-start invariant: importing this module must NOT trigger ``fastmcp``.
The ``serve`` subcommand is registered through :class:`LazyGroup` so its
implementation (which lives in :mod:`a2kit.packages.mcp.cli`) is only
imported when the user actually runs ``<app> serve``.

Progressive disclosure: top-level ``--help`` shows one entry per Router.
The user runs ``<app> <router-slug> --help`` to see that router's tools,
and ``<app> <router-slug> <tool> --help`` to see the tool's options.

App propagation: ``a2kit.run(app)`` builds the CLI here. Before Click
dispatches, we set the shared ``_APP_CTX`` ContextVar (imported from
:mod:`a2kit.packages.mcp.cli` per the Phase-3.1 convention) so lazy
subcommands can read the active App without any global mutable state.
"""

from __future__ import annotations

import inspect
import json
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast, get_type_hints

import click

from a2kit.metadata import get_meta
from a2kit.packages.cli.runtime import invoke_tool_sync
from a2kit.packages.cli.schemas import compute_schema, schema_command
from a2kit.packages.connections.cli import connections_group
from a2kit.packages.formatter import FormatHint, format_response
from a2kit.signature import user_input_params

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.app import App
    from a2kit.routers import Router


class LazyGroup(click.Group):
    """Click group with lazily-imported subcommands.

    ``lazy_subcommands`` maps subcommand name → ``"module.path:attribute"``.
    The module is only imported when the subcommand is actually resolved.
    """

    def __init__(
        self,
        *args: Any,
        lazy_subcommands: dict[str, str] | None = None,
        lazy_short_help: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._lazy: dict[str, str] = lazy_subcommands or {}
        self._lazy_short_help: dict[str, str] = lazy_short_help or {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self._lazy})

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._lazy:
            mod_path, attr = self._lazy[cmd_name].rsplit(":", 1)
            return getattr(import_module(mod_path), attr)
        return super().get_command(ctx, cmd_name)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        # Render lazy subcommands with their static short_help so `--help` does NOT
        # import them — preserves the cold-start invariant for `serve`.
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
    """Return the non-None branch of ``Optional[T]`` / ``T | None`` / ``Union[T, None]``.

    Returns ``annotation`` unchanged if it is not a nullable union of one type.
    """
    import types
    import typing

    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _click_type_for(annotation: Any) -> tuple[Any, bool]:
    """Map a Python type annotation to (click type, is_complex_json).

    Returns ``(click_type, False)`` for primitives Click handles natively
    (including nullable primitives like ``Optional[int]`` / ``int | None``),
    or ``(click.STRING, True)`` for complex types we'll JSON-decode at call time.
    """
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


def _make_tool_command(fn: Callable[..., Any]) -> click.Command:
    """Build a Click command that invokes ``fn`` with auto-derived options.

    Each user-input kwonly param becomes ``--name`` (or ``--flag/--no-flag``
    for bool, or a JSON-decoded string for complex types). Universal options:
    ``--format=auto|toon|json`` and a hidden ``--schema`` flag.
    """
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
            "required": False,  # enforced post-parse so --schema can bypass
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

        # Drop options the user did not pass (None & not required) — let
        # the underlying fn fall back to its declared default.
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
        try:
            data = invoke_tool_sync(fn, call_kwargs, fmt=fmt, ctx_param_name=ctx_param)
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


def _bind_if_method(fn: Callable[..., Any], router: Router) -> Callable[..., Any]:
    """Bind ``self`` to ``router`` when ``fn`` is an unbound class method.

    Routers store raw class-dict functions (so :class:`A2KitMeta` survives the
    descriptor protocol). For invocation we need ``self`` bound — but only
    if the function actually has a leading positional ``self``/``cls`` param.
    Preserves :class:`A2KitMeta` on the returned bound method.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    if not params or params[0].name not in ("self", "cls"):
        return fn

    import functools

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_bound(*args: Any, **kwargs: Any) -> Any:
            return await fn(router, *args, **kwargs)

        bound: Callable[..., Any] = async_bound
    else:

        @functools.wraps(fn)
        def sync_bound(*args: Any, **kwargs: Any) -> Any:
            return fn(router, *args, **kwargs)

        bound = sync_bound

    meta = get_meta(fn)
    if meta is not None:
        from a2kit.metadata import set_meta

        set_meta(bound, meta)
    # Strip the leading `self` from the wrapped function's signature so
    # `user_input_params` / `strip_dependencies` see only kwonly user args.
    new_sig = sig.replace(parameters=params[1:])
    # why: functools.wraps returns _Wrapped which doesn't expose __signature__ in stubs
    cast("Any", bound).__signature__ = new_sig
    return bound


def _router_group(router: Router) -> click.Group:
    """Build a Click group containing one subcommand per tool on ``router``."""
    group = click.Group(
        name=router.slug,
        help=f"Tools in router {router.slug!r}.",
    )
    for fn in router.tools():
        callable_ = _bind_if_method(fn, router)
        group.add_command(_make_tool_command(callable_))
    return group


def _wrap_main_with_app_ctx(group: click.Group, app: App) -> click.Group:
    """Patch ``group.main`` so ``_APP_CTX`` is set for the whole invocation."""
    orig_main = group.main

    def main_with_ctx(*a: Any, **k: Any) -> Any:
        from a2kit.packages.cli.app_ctx import _APP_CTX

        token = _APP_CTX.set(app)
        try:
            return orig_main(*a, **k)
        finally:
            _APP_CTX.reset(token)

    # why: monkey-patching click.Group.main with a wrapper of compatible runtime shape
    cast("Any", group).main = main_with_ctx
    return group


def build_full_cli(app: App) -> click.Command:
    """Build the top-level Click group for ``app``.

    Top-level commands:
      - one subgroup per Router (slug-named)
      - ``connections`` (eager)
      - ``schema`` (eager)
      - ``serve`` (LAZY — only this triggers a fastmcp import)
    """
    routers = list(app.routers())
    router_help_lines = [f"  {r.slug}  (run `{app.name} {r.slug} --help` for tools)" for r in routers]
    help_text = (app.name or "a2kit") + " — agent toolkit CLI."
    if router_help_lines:
        help_text += "\n\nRouters:\n" + "\n".join(router_help_lines)

    group = LazyGroup(
        name=app.name or "a2kit",
        help=help_text,
        lazy_subcommands={"serve": "a2kit.packages.mcp.cli:serve_command"},
        lazy_short_help={"serve": "Run as an MCP server (stdio or HTTP)."},
    )

    for router in routers:
        group.add_command(_router_group(router))
    group.add_command(connections_group)
    group.add_command(schema_command)

    _wrap_main_with_app_ctx(group, app)
    return group


__all__ = ["LazyGroup", "build_full_cli"]
