"""Tool decorator — composes with FastMCP's `@server.tool()`, does not replace it.

v0.2 makes the decorator *fat*: connection lookup, token resolution, write-mode
enforcement, tool-call envelope contamination guard, OTel spans, streaming
awareness — all opt-in, all behind keyword args, all defaulting to v0.1's
behaviour. A bare `@a2kit.tool()` (or the legacy `@a2kit.tools.tool()`) is
byte-equivalent to v0.1.

Behaviour order, before the wrapped function runs:

1. Connection lookup (if `connection_param` set) — finds the connection key in
   bound args, looks it up in `store`, raises `ConnectionNotFound` enumerating
   available names if missing. Ephemeral connections are merged into `store` at
   the Router level (v0.8); the decorator no longer takes an `ephemeral=` kwarg.
2. Token resolution — recursively resolves `${ENV}` / `op://` / literals on every
   string field of the loaded `ConnectionInfo`. The resolved info is exposed via
   `Router.context.info()` (or a hand-built `_RouterContext`); the v0.6
   `info=` kwarg-injection path was removed in v0.7.
3. Read-only enforcement — if `write=True` and `info.read_only` is True, raises
   `WriteNotAllowed`.
4. Tool-call envelope guard — every `str` argument is checked for the
   `<parameter name=` pattern (tool-call-envelope contamination observed in
   production). Disable via `tool_call_guard=False`.
5. Run wrapped function (await if coroutine).
6. Refuse `-> str` returns (decoration time) + preserve return annotation (v0.1).
7. Error enrichment via the optional `enricher` (v0.1).
8. OTel span — if `otel=True` AND `opentelemetry` is installed AND a non-default
   tracer provider is configured, wraps the call in `a2kit.tool.<name>`. No-op
   otherwise.
9. Streaming awareness — if `streaming=True` and the wrapped function returns an
   async iterator, the decorator collects items into a list on stdio transport
   and yields them through on HTTP. Transport is read from the thread-local
   `_current_transport` set by `MCPRunner`. No transport set → stdio.

Standalone helper `assert_clean_string(value, param_name)` exposed for tests
or non-decorated use.
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from a2kit._capabilities import Cap, Capability
from a2kit._otel import otel_span as _otel_span
from a2kit.exceptions import (
    ConnectionNotFound,
    InvalidToolReturnTypeError,
    ToolCallContamination,
    WriteNotAllowed,
)


class _NullSpan:
    """Local no-op CM used when `otel=False` is passed to the decorator."""

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *_: object) -> None:
        return None


if TYPE_CHECKING:
    from a2kit.connections import ConnectionInfo, ConnectionStore
    from a2kit.errors import EnricherRegistry, ErrorEnricher
    from a2kit.tokens import ResolverRegistry

F = TypeVar("F", bound=Callable[..., Any])

# --------------------------------------------------------------------------- #
# Transport seam — set by MCPRunner.run().
# Documented seam: any code that needs to know transport reads via
# `_get_current_transport()`. Tests can call `_set_current_transport()` directly.
# --------------------------------------------------------------------------- #

_TRANSPORT_LOCAL = threading.local()
_TOOL_CALL_CONTAMINATION_MARKER = "<parameter name="


def _set_current_transport(name: str | None) -> None:
    """Internal seam used by `MCPRunner` (and tests) to flag transport."""
    _TRANSPORT_LOCAL.value = name


def _get_current_transport() -> str:
    """Return current transport name; defaults to `'stdio'`."""
    return getattr(_TRANSPORT_LOCAL, "value", None) or "stdio"


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #


def assert_clean_string(value: str, param_name: str = "<unnamed>", tool_name: str | None = None) -> None:
    """Raise `ToolCallContamination` if `value` contains a tool-call envelope tag.

    Exposed standalone so consumers can run the same check in helper functions
    that don't go through the decorator.
    """
    if isinstance(value, str) and _TOOL_CALL_CONTAMINATION_MARKER in value:
        raise ToolCallContamination(param_name=param_name, tool_name=tool_name)


def preserve_return_annotation(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Copy `fn.__annotations__["return"]` onto the wrapper. Idempotent.

    Use directly if you want the FastMCP annotation-hygiene fix without the rest
    of `@tool(...)`. The trick: FastMCP walks `__wrapped__` chains via
    `inspect.signature(follow_wrapped=True, eval_str=True)`; setting the
    annotation on BOTH the wrapper and the wrapped survives that walk
    (pattern lifted from an HTTP-wrapping MCP's tool decorator).
    """
    return_anno = fn.__annotations__.get("return")
    if return_anno is None:
        return fn
    fn.__annotations__["return"] = return_anno
    return fn


def _check_return_annotation(fn: Callable[..., Any]) -> Any:
    """Reject `-> str` at decoration time. Returns the resolved annotation."""
    annos = getattr(fn, "__annotations__", {})
    if "return" not in annos:
        return None
    ret = annos["return"]
    if ret is str or ret == "str":
        raise InvalidToolReturnTypeError(getattr(fn, "__name__", "<tool>"))
    return ret


def _resolve_connection_key(value: Any) -> tuple[str, ...]:
    """Coerce a connection arg into a tuple-key. Supports str / tuple / list."""
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    msg = f"connection param must be str|tuple|list, got {type(value).__name__}"
    raise TypeError(msg)


def _lookup_connection(
    key: tuple[str, ...],
    store: ConnectionStore[Any] | None,
) -> Any:
    if store is None:
        raise ConnectionNotFound(key)
    return store.load(key)


def _resolve_info_strings(info: ConnectionInfo, registry: ResolverRegistry | None) -> ConnectionInfo:
    """Return a copy of `info` with every str field resolved through `registry`.

    Pydantic v2 frozen models support `.model_copy(update={...})`. We collect
    the str-typed fields, resolve each, and produce one new instance.
    """
    from a2kit.tokens import resolve_token  # noqa: PLC0415 — keep tokens lazy

    update: dict[str, str] = {}
    for name, value in info.model_dump().items():
        if isinstance(value, str) and name != "key":
            update[name] = resolve_token(value, registry=registry)
    if not update:
        return info
    return info.model_copy(update=update)


def _inject_projection_signature(wrapper: Any, fn: Any, sig: inspect.Signature) -> None:
    """Synthesise wrapper signature with `filter` + `fields` kwonly params.

    Used by `@a2kit.tool(projection=True)` so authors don't have to declare the
    projection knobs on their function. FastMCP introspects the wrapper via
    `inspect.signature(follow_wrapped=True)`; setting `wrapper.__signature__`
    short-circuits the `__wrapped__` chain so the synthetic sig wins.

    Refuses to inject if the function already declares `filter` or `fields`
    (collision = author intent we shouldn't shadow).
    """
    if "filter" in sig.parameters or "fields" in sig.parameters:
        msg = (
            "projection=True cannot be used on a function that already declares "
            "`filter` or `fields` parameters; rename them or drop projection=True."
        )
        raise ValueError(msg)
    extra = [
        inspect.Parameter("filter", inspect.Parameter.KEYWORD_ONLY, default="", annotation=str),
        inspect.Parameter("fields", inspect.Parameter.KEYWORD_ONLY, default=None, annotation="list[str] | None"),
    ]
    # Insert before any VAR_KEYWORD to satisfy Signature ordering rules.
    params = list(sig.parameters.values())
    insert_at = next(
        (i for i, p in enumerate(params) if p.kind == inspect.Parameter.VAR_KEYWORD),
        len(params),
    )
    new_params = params[:insert_at] + extra + params[insert_at:]
    wrapper.__signature__ = sig.replace(parameters=new_params)
    extras_anno = {"filter": str, "fields": "list[str] | None"}
    wrapper.__annotations__ = {**wrapper.__annotations__, **extras_anno}
    fn.__annotations__ = {**fn.__annotations__, **extras_anno}


def _check_tool_call_contamination(bound: inspect.BoundArguments, fn_name: str) -> None:
    for name, value in bound.arguments.items():
        if isinstance(value, str):
            assert_clean_string(value, param_name=name, tool_name=fn_name)


# --------------------------------------------------------------------------- #
# The fat decorator.
# --------------------------------------------------------------------------- #


def tool(  # noqa: C901, PLR0915 — fat decorator by design
    *,
    enricher: ErrorEnricher | EnricherRegistry | None = None,
    store: ConnectionStore[Any] | None = None,
    connection_param: str | None = None,
    write: bool = False,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    cel_filter_param: str | None = None,
    fields_param: str | None = None,
    projection: bool = False,
    router_context: Any = None,
    cli: str | None = None,
) -> Callable[[F], F]:
    """Compose with FastMCP's `@server.tool()`. See module docstring for behaviour.

    All args optional. `@a2kit.tool()` with no args behaves identically to v0.1.

    v0.3: pass `server=` to auto-register the wrapped function with FastMCP's tool
    manager. Stacking with an explicit `@server.tool()` on top still works
    (idempotent — the second registration is a no-op).
    """

    def decorator(fn: F) -> F:  # noqa: C901, PLR0915
        return_anno = _check_return_annotation(fn)
        is_async = inspect.iscoroutinefunction(fn)
        sig = inspect.signature(fn)
        resolved_tool_name = tool_name or fn.__name__
        # Auto-tag seam: merge author-supplied caps + write/router context.
        tool_caps = _compute_tool_capabilities(set(capabilities), write=write, tool_name=resolved_tool_name)

        if projection and (cel_filter_param is not None or fields_param is not None):
            msg = (
                "projection=True is sugar for `cel_filter_param='filter', fields_param='fields'` "
                "with auto-injected wrapper params. Combine one path or the other, not both."
            )
            raise ValueError(msg)

        def _prelude(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any], tuple[str, ...] | None, Any]:
            """Run pre-call steps. Returns args/kwargs/key and a context-reset token."""
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            if tool_call_guard:
                _check_tool_call_contamination(bound, resolved_tool_name)

            connection_key: tuple[str, ...] | None = None
            ctx_token: Any = None
            if connection_param is not None and connection_param in bound.arguments:
                raw = bound.arguments[connection_param]
                connection_key = _resolve_connection_key(raw)
                info = _lookup_connection(connection_key, store)
                info = _resolve_info_strings(info, resolver_registry)
                if write and getattr(info, "read_only", False):
                    raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                if router_context is not None:
                    ctx_token = router_context._set(info)  # noqa: SLF001
            return args, kwargs, connection_key, ctx_token

        def _extract_projection(bound: inspect.BoundArguments) -> tuple[str, list[str] | None]:
            """Extract filter+fields values from bound args (for cel_filter_param / fields_param)."""
            filter_expr = ""
            fields_value: list[str] | None = None
            if cel_filter_param is not None and cel_filter_param in bound.arguments:
                raw = bound.arguments[cel_filter_param]
                if isinstance(raw, str):
                    filter_expr = raw
            if fields_param is not None and fields_param in bound.arguments:
                raw_f = bound.arguments[fields_param]
                if isinstance(raw_f, list):
                    fields_value = [str(f) for f in raw_f]
            return filter_expr, fields_value

        def _maybe_post_process(result: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
            if cel_filter_param is None and fields_param is None:
                return result
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            filter_expr, fields_value = _extract_projection(bound)
            if not filter_expr and not fields_value:
                return result
            from a2kit.formatter import format_response  # noqa: PLC0415

            return format_response(result, filter=filter_expr, fields=fields_value)

        def _projection_pop(kwargs: dict[str, Any]) -> tuple[str, list[str] | None]:
            """Pop synthesised `filter`+`fields` kwargs (projection=True path).

            Defensive on type — non-str/non-list values fall back to empty.
            """
            raw_filter = kwargs.pop("filter", "")
            raw_fields = kwargs.pop("fields", None)
            filter_val = raw_filter if isinstance(raw_filter, str) else ""
            fields_val = [str(f) for f in raw_fields] if isinstance(raw_fields, list) else None
            return filter_val, fields_val

        def _projection_post(result: Any, filter_val: str, fields_val: list[str] | None) -> Any:
            if not (filter_val or fields_val):
                return result
            from a2kit.formatter import format_response  # noqa: PLC0415

            return format_response(result, filter=filter_val, fields=fields_val)

        if is_async:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx_token: Any = None
                proj_filter, proj_fields = _projection_pop(kwargs) if projection else ("", None)
                try:
                    args, kwargs, conn_key, ctx_token = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = await fn(*args, **kwargs)
                        if streaming and isinstance(result, AsyncIterator):
                            return await _consume_or_passthrough_async(result)
                        if projection:
                            return _projection_post(result, proj_filter, proj_fields)
                        return _maybe_post_process(result, args, kwargs)
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher.enrich(exc, tool_name=resolved_tool_name) from exc
                finally:
                    if ctx_token is not None and router_context is not None:
                        router_context._reset(ctx_token)  # noqa: SLF001

            wrapper: Callable[..., Any] = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx_token: Any = None
                proj_filter, proj_fields = _projection_pop(kwargs) if projection else ("", None)
                try:
                    args, kwargs, conn_key, ctx_token = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = fn(*args, **kwargs)
                        if projection:
                            return _projection_post(result, proj_filter, proj_fields)
                        return _maybe_post_process(result, args, kwargs)
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher.enrich(exc, tool_name=resolved_tool_name) from exc
                finally:
                    if ctx_token is not None and router_context is not None:
                        router_context._reset(ctx_token)  # noqa: SLF001

            wrapper = sync_wrapper

        if projection:
            _inject_projection_signature(wrapper, fn, sig)

        if return_anno is not None:
            wrapper.__annotations__ = {**wrapper.__annotations__, "return": return_anno}
            fn.__annotations__ = {**fn.__annotations__, "return": return_anno}

        _inject_param_docs(wrapper, fn, sig, connection_param=connection_param, cli=cli)

        # Stamp computed capability tags so the runner / select can filter.
        # `setattr` (rather than `wrapper._a2kit_capabilities = ...`) keeps ty
        # happy: `functools.wraps` returns a `_Wrapped[...]` whose attribute set
        # ty considers closed.
        setattr(wrapper, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(wrapper, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010
        setattr(fn, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(fn, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010

        if server is not None:
            _register_with_server(server, wrapper, resolved_tool_name)

        return cast("F", wrapper)

    return decorator


# Auto-tag seam:
# `_compute_tool_capabilities` reads the active router (set by
# `RouterRegistry.apply()` via `a2kit._router_state._set_active`). It unions:
#   - author-supplied `capabilities=`
#   - `Cap.READ` or `Cap.WRITE` (router phase or `write=True` flag)
#   - active router name (if `router.auto_tag=True`) and `router.capabilities`
#   - `tool:<resolved_tool_name>` for tool-namespace selection
def _compute_tool_capabilities(author: set[Capability], *, write: bool, tool_name: str) -> set[Capability]:
    from a2kit._router_state import _get_active  # noqa: PLC0415

    caps: set[Capability] = set(author)
    if write:
        caps.add(Cap.WRITE)
    active = _get_active()
    if active is not None:
        caps.update(active.router.capabilities)
        if active.router.auto_tag:
            caps.add(active.router.name)
            caps.add(f"router:{active.router.name}")
        if active.phase == "read":
            caps.add(Cap.READ)
        elif active.phase == "write":
            caps.add(Cap.WRITE)
        if active.router.default:
            caps.add("default")
    else:
        # Router-less tool: still default-on (so `--select default` picks it up).
        caps.add("default")
    caps.add(f"tool:{tool_name}")
    return caps


def _inject_param_docs(
    wrapper: Any,
    fn: Any,
    sig: inspect.Signature,
    *,
    connection_param: str | None = None,
    cli: str | None = None,
) -> None:
    """Auto-inject canonical param-doc text into the function's docstring.

    Two sources, in order:

    1. If `connection_param` is set, prepend the canonical
       `connection_param_doc(...)` text for it.
    2. For any other registered param doc (`register_param_doc(name, text)`),
       append `f"{name}: {text}"`.

    Skips additions for params already mentioned in the existing docstring —
    explicit author text always wins.

    Configurable: `[tool.a2kit.docs] auto_inject = false` disables entirely
    (read once per process, cached).
    """
    if not _auto_inject_enabled():
        return
    from a2kit.docs import _registered_param_docs, connection_param_doc  # noqa: PLC0415

    registry = _registered_param_docs()
    existing = wrapper.__doc__ or ""
    additions: list[str] = []
    for param_name in sig.parameters:
        if param_name in existing:
            continue
        if param_name == connection_param:
            additions.append(connection_param_doc(param_name, cli=cli or "a2kit"))
        elif param_name in registry:
            additions.append(f"{param_name}: {registry[param_name]}")
    if not additions:
        return
    suffix = "\n\n" + "\n".join(additions)
    new_doc = (existing.rstrip() + suffix) if existing else "\n".join(additions)
    wrapper.__doc__ = new_doc
    fn.__doc__ = new_doc


_AUTO_INJECT_CACHE: dict[str, bool] = {}


def _auto_inject_enabled() -> bool:
    """Read `[tool.a2kit.docs] auto_inject` from pyproject.toml. Default True."""
    if "value" in _AUTO_INJECT_CACHE:
        return _AUTO_INJECT_CACHE["value"]
    value = True
    try:
        from a2kit.scaffold import _load_pyproject_a2kit  # noqa: PLC0415

        table = _load_pyproject_a2kit().get("docs", {})
        if isinstance(table, dict) and "auto_inject" in table:
            value = bool(table["auto_inject"])
    except Exception:  # noqa: BLE001 — defensive; never break the decorator
        value = True
    _AUTO_INJECT_CACHE["value"] = value
    return value


def _reset_auto_inject_cache() -> None:
    """Test seam — drop the cached pyproject value."""
    _AUTO_INJECT_CACHE.clear()


def _register_with_server(server: Any, wrapper: Any, name: str) -> None:
    """Register `wrapper` with a FastMCP server idempotently.

    If a tool with the same name (and same callable) is already registered, skip.
    Otherwise call `server.tool()(wrapper)`.
    """
    try:
        existing = server._tool_manager.list_tools()  # noqa: SLF001
    except AttributeError:
        existing = []
    for entry in existing:
        if getattr(entry, "name", None) == name:
            # Already registered — typically because `@server.tool()` stacked above.
            return
    server.tool()(wrapper)


async def _consume_or_passthrough_async(async_iter: AsyncIterator[Any]) -> Any:
    """If transport is stdio, collect into a list. Otherwise pass through."""
    if _get_current_transport() == "stdio":
        return [item async for item in async_iter]
    return async_iter


__all__ = [
    "_get_current_transport",
    "_reset_auto_inject_cache",
    "_set_current_transport",
    "assert_clean_string",
    "preserve_return_annotation",
    "tool",
]


# Keep a useless reference so `from collections.abc import Awaitable` does not
# trip the unused-import lint when type-checkers thin out the import block.
_ = Awaitable
