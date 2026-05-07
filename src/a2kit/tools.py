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
from a2kit.formatter import FormatName, ListViewMode, Page, format_from_annotation


class _NullSpan:
    """Local no-op CM used when `otel=False` is passed to the decorator."""

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *_: object) -> None:
        return None


if TYPE_CHECKING:
    from a2kit.connections import ConnectionInfo, ConnectionStore
    from a2kit.errors import EnricherFn
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


def _resolve_return_annotation(fn: Any, raw: Any) -> Any:
    """Resolve a possibly string-form return annotation to its runtime type.

    Under `from __future__ import annotations`, `fn.__annotations__["return"]`
    is a string. Use `inspect.get_annotations(eval_str=True)` so format-from-
    type detection sees `list[Row]` rather than `"list[Row]"`.
    """
    if raw is None or not isinstance(raw, str):
        return raw
    try:
        hints = inspect.get_annotations(fn, eval_str=True)
    except (NameError, AttributeError, SyntaxError):
        # Forward refs / non-toplevel names / malformed annotations — safe to
        # fall back. Other exceptions (TypeError, etc.) are real bugs and bubble.
        return None
    return hints.get("return")


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


def _detect_info_param(fn: Any, sig: inspect.Signature) -> tuple[str, type] | None:
    """Type-driven info DI — find a `ConnectionInfo`-typed param on `fn`.

    Returns ``(param_name, info_class)`` if exactly one such param exists;
    ``None`` if zero. Raises if more than one — multi-info tools aren't a
    pattern we support (use `Router.context.info()` from a helper if you
    really need cross-context access).
    """
    from a2kit.connections import ConnectionInfo  # noqa: PLC0415

    try:
        hints = inspect.get_annotations(fn, eval_str=True)
    except (NameError, AttributeError):  # pragma: no cover — forward-ref fallback
        # Forward refs that don't resolve — fall back to raw annotations.
        hints = getattr(fn, "__annotations__", {})

    matches: list[tuple[str, type]] = []
    for name in sig.parameters:
        anno = hints.get(name)
        if isinstance(anno, type) and issubclass(anno, ConnectionInfo):
            matches.append((name, anno))
    if not matches:
        return None
    if len(matches) > 1:
        names = [m[0] for m in matches]
        msg = (
            f"Tool {fn.__name__!r} declares multiple ConnectionInfo-typed "
            f"parameters {names}. Only one info-injection target is supported "
            "per tool; use `Router.context.info()` from a helper for "
            "cross-context access."
        )
        raise ValueError(msg)
    return matches[0]


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


def _listview_local_params(
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> list[inspect.Parameter]:
    """Build kwonly params the kit injects for **Local** concerns.

    Passthrough concerns are owned by the function — the author declares
    them in the signature directly. Local concerns are kit-owned: the
    function never sees them, so we splice them into the wrapper sig.
    """
    extra: list[inspect.Parameter] = []
    kwonly = inspect.Parameter.KEYWORD_ONLY
    if filter_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("filter", kwonly, default="", annotation=str))
    if fields_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("fields", kwonly, default=None, annotation="list[str] | None"))
    if pagination_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("limit", kwonly, default=50, annotation=int))
        extra.append(inspect.Parameter("cursor", kwonly, default=None, annotation="str | None"))
    return extra


def _verify_passthrough_params(
    fn: Any,
    sig: inspect.Signature,
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> None:
    """Each Passthrough concern requires its param on the fn signature.

    Mode mismatch is an author bug — fail loudly at decoration so the agent
    never sees a tool that promises filter/fields/pagination passthrough
    but silently drops the kwarg.
    """
    expected: list[str] = []
    if filter_mode is ListViewMode.PASSTHROUGH:
        expected.append("filter")
    if fields_mode is ListViewMode.PASSTHROUGH:
        expected.append("fields")
    if pagination_mode is ListViewMode.PASSTHROUGH:
        expected.extend(("limit", "cursor"))
    missing = [name for name in expected if name not in sig.parameters]
    if missing:
        msg = (
            f"Passthrough mode declared on {fn.__name__!r} but the function does "
            f"not accept {missing}. Either declare them in your function "
            "signature (Passthrough = your tool body handles them) or switch "
            "the matching decorator kwarg to Local."
        )
        raise ValueError(msg)


def _splice_wrapper_signature(
    wrapper: Any,
    fn: Any,
    sig: inspect.Signature,
    extra: list[inspect.Parameter],
    *,
    hide_names: set[str] | None = None,
) -> None:
    """Build the agent-facing wrapper signature.

    - Splices `extra` (kit-injected kwonly params: `connection`, list-view
      knobs) before any VAR_KEYWORD on the fn.
    - Removes any params named in `hide_names` (used to hide DI-injected
      params like the typed `info: WidgetConn`).

    FastMCP reads `inspect.signature(wrapper, follow_wrapped=True)`;
    setting `wrapper.__signature__` short-circuits the `__wrapped__` walk so
    the synthetic sig wins.
    """
    hide = hide_names or set()
    if not extra and not hide:
        return
    collisions = [p.name for p in extra if p.name in sig.parameters]
    if collisions:
        msg = (
            f"Kit-injected params {collisions} collide with parameters "
            f"declared on {fn.__name__!r}. Either rename your function param, "
            "drop the matching decorator kwarg, or switch list-view modes to "
            "Passthrough."
        )
        raise ValueError(msg)
    params = [p for name, p in sig.parameters.items() if name not in hide]
    insert_at = next(
        (i for i, p in enumerate(params) if p.kind == inspect.Parameter.VAR_KEYWORD),
        len(params),
    )
    new_params = params[:insert_at] + extra + params[insert_at:]
    wrapper.__signature__ = sig.replace(parameters=new_params)
    extras_anno = {p.name: p.annotation for p in extra}
    wrapper.__annotations__ = {k: v for k, v in {**wrapper.__annotations__, **extras_anno}.items() if k not in hide}
    fn.__annotations__ = {**fn.__annotations__, **extras_anno}


# --- Cursor encoding (Local pagination) -------------------------------------- #


def _encode_cursor(offset: int) -> str:
    """Opaque base64 string from an integer offset."""
    import base64  # noqa: PLC0415

    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    """Reverse `_encode_cursor`. Invalid input → 0 (start of list)."""
    if not cursor:
        return 0
    import base64  # noqa: PLC0415

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return max(0, int(base64.urlsafe_b64decode(padded.encode()).decode()))
    except (ValueError, UnicodeDecodeError):
        return 0


# --- Listview pop + post-process pipeline ----------------------------------- #


def _listview_extract_local(
    kwargs: dict[str, Any],
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> dict[str, Any]:
    """Pop Local concern kwargs out of `kwargs` so the fn never sees them.

    Passthrough kwargs stay in `kwargs` for the fn body to handle.
    Returns a state dict with whatever the kit needs for post-processing.
    """
    state: dict[str, Any] = {}
    if filter_mode is ListViewMode.LOCAL:
        raw = kwargs.pop("filter", "")
        state["filter"] = raw if isinstance(raw, str) else ""
    if fields_mode is ListViewMode.LOCAL:
        raw_f = kwargs.pop("fields", None)
        state["fields"] = [str(f) for f in raw_f] if isinstance(raw_f, list) else None
    if pagination_mode is ListViewMode.LOCAL:
        raw_limit = kwargs.pop("limit", 50)
        state["limit"] = raw_limit if isinstance(raw_limit, int) and raw_limit > 0 else 50
        state["cursor"] = kwargs.pop("cursor", None)
    return state


def _listview_apply(
    result: Any,
    state: dict[str, Any],
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
    format_hint: FormatName | None = None,
) -> Any:
    """Pipeline: unwrap Page → local filter → local fields → local paginate → Response.

    If `result` isn't a list or Page (e.g. a scalar / single dict), bypass
    list-view processing and return as-is. Pydantic-model items are dumped
    to dicts so the tabular encoder sees flat rows.
    """
    from a2kit.formatter import _dump_items as _fmt_dump_items  # noqa: PLC0415

    next_cursor: str | None = None
    items: list[dict[str, Any]]
    if isinstance(result, Page):
        items = _fmt_dump_items(list(result.items))
        next_cursor = result.next_cursor
    elif isinstance(result, list):
        items = _fmt_dump_items(result)
    else:
        return result  # not a list-view-shaped result, leave alone

    if filter_mode is ListViewMode.LOCAL and state.get("filter"):
        from a2kit import projection  # noqa: PLC0415

        items = list(projection.filter_records(items, expr=state["filter"]))

    if fields_mode is ListViewMode.LOCAL and state.get("fields"):
        from a2kit import projection  # noqa: PLC0415

        items = list(projection.project_fields(items, fields=state["fields"]))

    if pagination_mode is ListViewMode.LOCAL:
        limit = state.get("limit", 50)
        offset = _decode_cursor(state.get("cursor"))
        sliced = items[offset : offset + limit]
        next_cursor = _encode_cursor(offset + limit) if offset + limit < len(items) else None
        items = sliced

    from a2kit.formatter import Response, format_response  # noqa: PLC0415

    base = format_response(items, format_hint=format_hint)
    return Response(format=base.format, data=base.data, truncated=base.truncated, next_cursor=next_cursor)


def _check_tool_call_contamination(bound: inspect.BoundArguments, fn_name: str) -> None:
    for name, value in bound.arguments.items():
        if isinstance(value, str):
            assert_clean_string(value, param_name=name, tool_name=fn_name)


# --------------------------------------------------------------------------- #
# The fat decorator.
# --------------------------------------------------------------------------- #


def tool(  # noqa: C901, PLR0915 — fat decorator by design
    *,
    enricher: EnricherFn | None = None,
    store: ConnectionStore[Any] | None = None,
    connection: bool = True,
    connection_param: str | None = None,  # v0.9: deprecated, kept as soft alias; drops in v0.10
    write: bool = False,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    filter: ListViewMode | None = None,  # noqa: A002
    fields: ListViewMode | None = None,
    pagination: ListViewMode | None = None,
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
        # Precompute the wire format from the return type. Locked at decoration
        # so each call skips a 1-2 dict walks; ``None`` falls back to runtime.
        # Resolve string annotations (PEP 563 / `from __future__ import annotations`).
        resolved_return_anno = _resolve_return_annotation(fn, return_anno)
        precomputed_format: FormatName | None = format_from_annotation(resolved_return_anno) if resolved_return_anno is not None else None
        is_async = inspect.iscoroutinefunction(fn)
        sig = inspect.signature(fn)
        resolved_tool_name = tool_name or fn.__name__
        # Auto-tag seam: merge author-supplied caps + write/router context.
        tool_caps = _compute_tool_capabilities(set(capabilities), write=write, tool_name=resolved_tool_name)

        # List-view modes (filter / fields / pagination) — verify Passthrough
        # params exist on fn at decoration time. Local params are injected later.
        _verify_passthrough_params(
            fn,
            sig,
            filter_mode=filter,
            fields_mode=fields,
            pagination_mode=pagination,
        )
        has_listview = filter is not None or fields is not None or pagination is not None

        # Connection handling — three modes:
        #   1) connection=False         → no connection (utility tool)
        #   2) connection_param=<name>  → legacy v0.8 path (deprecated, drops v0.10)
        #   3) connection=True (default) → typed-info DI (v0.9 idiom)
        info_target: tuple[str, type] | None = None
        needs_connection_arg = False
        if connection and connection_param is None:
            info_target = _detect_info_param(fn, sig)
            needs_connection_arg = info_target is not None or store is not None

        def _prelude(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any], tuple[str, ...] | None, Any]:  # noqa: C901
            """Run pre-call steps. Returns args/kwargs/key and a context-reset token."""
            connection_key: tuple[str, ...] | None = None
            ctx_token: Any = None

            if needs_connection_arg:
                # v0.9 path: kit injected `connection: str` into wrapper sig.
                # Pop it before fn receives kwargs; bind resolved info to typed param.
                raw = kwargs.pop("connection", None)
                if raw is None:
                    msg = f"Tool {resolved_tool_name!r} requires a `connection` argument (the saved connection key)."
                    raise TypeError(msg)
                connection_key = _resolve_connection_key(raw)
                info = _lookup_connection(connection_key, store)
                info = _resolve_info_strings(info, resolver_registry)
                if write and getattr(info, "read_only", False):
                    raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                if router_context is not None:
                    ctx_token = router_context._set(info)  # noqa: SLF001
                if info_target is not None:
                    kwargs[info_target[0]] = info
            elif connection_param is not None:
                # v0.8 legacy path — fn declares the param itself; we look it up
                # by name in bound args. Deprecated; drops in v0.10.
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                if connection_param in bound.arguments:
                    raw = bound.arguments[connection_param]
                    connection_key = _resolve_connection_key(raw)
                    info = _lookup_connection(connection_key, store)
                    info = _resolve_info_strings(info, resolver_registry)
                    if write and getattr(info, "read_only", False):
                        raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                    if router_context is not None:
                        ctx_token = router_context._set(info)  # noqa: SLF001

            # Tool-call envelope guard runs after kwargs mutation so the
            # injected info object isn't pattern-matched as contaminated text.
            if tool_call_guard:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                _check_tool_call_contamination(bound, resolved_tool_name)

            return args, kwargs, connection_key, ctx_token

        if is_async:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx_token: Any = None
                lv_state = (
                    _listview_extract_local(
                        kwargs,
                        filter_mode=filter,
                        fields_mode=fields,
                        pagination_mode=pagination,
                    )
                    if has_listview
                    else {}
                )
                try:
                    args, kwargs, conn_key, ctx_token = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = await fn(*args, **kwargs)
                        if streaming and isinstance(result, AsyncIterator):
                            return await _consume_or_passthrough_async(result)
                        if has_listview:
                            return _listview_apply(
                                result,
                                lv_state,
                                filter_mode=filter,
                                fields_mode=fields,
                                pagination_mode=pagination,
                                format_hint=precomputed_format,
                            )
                        return result
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher(exc, resolved_tool_name) from exc
                finally:
                    if ctx_token is not None and router_context is not None:
                        router_context._reset(ctx_token)  # noqa: SLF001

            wrapper: Callable[..., Any] = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                ctx_token: Any = None
                lv_state = (
                    _listview_extract_local(
                        kwargs,
                        filter_mode=filter,
                        fields_mode=fields,
                        pagination_mode=pagination,
                    )
                    if has_listview
                    else {}
                )
                try:
                    args, kwargs, conn_key, ctx_token = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = fn(*args, **kwargs)
                        if has_listview:
                            return _listview_apply(
                                result,
                                lv_state,
                                filter_mode=filter,
                                fields_mode=fields,
                                pagination_mode=pagination,
                                format_hint=precomputed_format,
                            )
                        return result
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher(exc, resolved_tool_name) from exc
                finally:
                    if ctx_token is not None and router_context is not None:
                        router_context._reset(ctx_token)  # noqa: SLF001

            wrapper = sync_wrapper

        # Build the kit-injected param list: `connection: str` (if applicable)
        # then Local list-view params. All splice in front of any VAR_KEYWORD.
        injected: list[inspect.Parameter] = []
        if needs_connection_arg:
            injected.append(
                inspect.Parameter(
                    "connection",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=inspect.Parameter.empty,
                    annotation=str,
                )
            )
        injected.extend(_listview_local_params(filter_mode=filter, fields_mode=fields, pagination_mode=pagination))
        # Hide the typed info-target param from the agent-facing schema —
        # FastMCP introspects via the wrapper, so we strip it here.
        hide_names: set[str] = {info_target[0]} if info_target is not None else set()
        _splice_wrapper_signature(wrapper, fn, sig, injected, hide_names=hide_names)

        if return_anno is not None:
            wrapper.__annotations__ = {**wrapper.__annotations__, "return": return_anno}
            fn.__annotations__ = {**fn.__annotations__, "return": return_anno}

        # Auto-inject param docs. The injected `connection: str` (when present)
        # is the agent-facing key — its docstring matters more than fn's typed
        # info param (which the agent never sees). Legacy connection_param=
        # uses its own name.
        doc_connection_param = "connection" if needs_connection_arg else connection_param
        _inject_param_docs(
            wrapper,
            fn,
            sig,
            connection_param=doc_connection_param,
            cli=cli,
            available_connections=_safe_list_connection_keys(store),
        )

        # Stamp computed capability tags so the runner / select can filter.
        # `setattr` (rather than `wrapper._a2kit_capabilities = ...`) keeps ty
        # happy: `functools.wraps` returns a `_Wrapped[...]` whose attribute set
        # ty considers closed.
        setattr(wrapper, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(wrapper, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010
        setattr(wrapper, "_a2kit_format", precomputed_format)  # noqa: B010
        setattr(fn, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(fn, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010
        setattr(fn, "_a2kit_format", precomputed_format)  # noqa: B010

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


def _safe_list_connection_keys(store: Any) -> list[str] | None:
    """Best-effort list of saved connection keys for schema enrichment.

    Returns ``None`` if the store can't list (no method, missing dir, etc.) so
    the docstring builder uses the generic phrasing instead.
    """
    if store is None or not hasattr(store, "list_connections"):
        return None
    try:
        return ["-".join(info.key) for info in store.list_connections()]
    except Exception:  # noqa: BLE001 — never fail decoration on store I/O issues
        return None


def _inject_param_docs(
    wrapper: Any,
    fn: Any,
    sig: inspect.Signature,
    *,
    connection_param: str | None = None,
    cli: str | None = None,
    available_connections: list[str] | None = None,
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
    # Use wrapper's spliced signature if set (so kit-injected `connection` is
    # iterated alongside fn-declared params).
    effective_sig = getattr(wrapper, "__signature__", None) or sig
    for param_name in effective_sig.parameters:
        if param_name in existing:
            continue
        if param_name == connection_param:
            additions.append(
                connection_param_doc(
                    param_name,
                    cli=cli or "a2kit",
                    available=available_connections,
                )
            )
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
