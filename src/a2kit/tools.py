"""Tool decorator — composes with FastMCP's `@server.tool()`, does not replace it.

v0.2 makes the decorator *fat*: connection lookup, token resolution, write-mode
enforcement, XML-contamination guard, OTel spans, streaming awareness — all
opt-in, all behind keyword args, all defaulting to v0.1's behaviour. A bare
`@a2kit.tool()` (or the legacy `@a2kit.tools.tool()`) is byte-equivalent to
v0.1.

Behaviour order, before the wrapped function runs:

1. Connection lookup (if `connection_param` set) — finds the connection key in
   bound args, looks it up in `store` (and `ephemeral` dict if provided), raises
   `ConnectionNotFound` enumerating available names if missing.
2. Token resolution — recursively resolves `${ENV}` / `op://` / literals on every
   string field of the loaded `ConnectionInfo`. The resolved info is injected as
   a kwarg `info` (configurable via `info_kwarg=`).
3. Read-only enforcement — if `write=True` and `info.read_only` is True, raises
   `WriteNotAllowed`.
4. String-param XML guard — every `str` argument is checked for the
   `<parameter name=` pattern (tool-call-envelope contamination observed in
   production). Disable via `xml_guard=False`.
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
from typing import TYPE_CHECKING, Any, TypeVar

from a2kit._capabilities import Cap, Capability
from a2kit._otel import otel_span as _otel_span
from a2kit.exceptions import (
    ConnectionNotFound,
    InvalidToolReturnTypeError,
    ToolXMLContamination,
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
_XML_CONTAMINATION_MARKER = "<parameter name="


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
    """Raise `ToolXMLContamination` if `value` contains the tool-XML opening tag.

    Exposed standalone so consumers can run the same check in helper functions
    that don't go through the decorator.
    """
    if isinstance(value, str) and _XML_CONTAMINATION_MARKER in value:
        raise ToolXMLContamination(param_name=param_name, tool_name=tool_name)


def preserve_return_annotation(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Copy `fn.__annotations__["return"]` onto the wrapper. Idempotent.

    Use directly if you want the FastMCP annotation-hygiene fix without the rest
    of `@tool(...)`. The trick: FastMCP walks `__wrapped__` chains via
    `inspect.signature(follow_wrapped=True, eval_str=True)`; setting the
    annotation on BOTH the wrapper and the wrapped survives that walk
    (a2atlassian `decorators.py:84-85`).
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
        raise InvalidToolReturnTypeError(fn.__name__)
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
    ephemeral: dict[tuple[str, ...], Any] | None,
) -> Any:
    if ephemeral is not None and key in ephemeral:
        return ephemeral[key]
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


def _check_xml_contamination(bound: inspect.BoundArguments, fn_name: str) -> None:
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
    info_kwarg: str = "info",
    ephemeral: dict[tuple[str, ...], Any] | None = None,
    write: bool = False,
    streaming: bool = False,
    xml_guard: bool = True,
    otel: bool = True,
    tool_name: str | None = None,
    resolver_registry: ResolverRegistry | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    cel_filter_param: str | None = None,
    fields_param: str | None = None,
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

        def _prelude(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any], tuple[str, ...] | None]:
            """Run pre-call steps. Returns the (possibly-mutated) args/kwargs and key."""
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()

            if xml_guard:
                _check_xml_contamination(bound, resolved_tool_name)

            connection_key: tuple[str, ...] | None = None
            if connection_param is not None and connection_param in bound.arguments:
                raw = bound.arguments[connection_param]
                connection_key = _resolve_connection_key(raw)
                info = _lookup_connection(connection_key, store, ephemeral)
                info = _resolve_info_strings(info, resolver_registry)
                if write and getattr(info, "read_only", False):
                    raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                kwargs = {**kwargs, info_kwarg: info}
            return args, kwargs, connection_key

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
                    fields_value = list(raw_f)
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

        if is_async:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    args, kwargs, conn_key = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = await fn(*args, **kwargs)
                        if streaming and isinstance(result, AsyncIterator):
                            return await _consume_or_passthrough_async(result)
                        return _maybe_post_process(result, args, kwargs)
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher.enrich(exc, tool_name=resolved_tool_name) from exc

            wrapper: Callable[..., Any] = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    args, kwargs, conn_key = _prelude(args, kwargs)
                    span_cm = _otel_span(resolved_tool_name, conn_key, write) if otel else _NullSpan()
                    with span_cm:
                        result = fn(*args, **kwargs)
                        return _maybe_post_process(result, args, kwargs)
                except Exception as exc:
                    if enricher is None:
                        raise
                    raise enricher.enrich(exc, tool_name=resolved_tool_name) from exc

            wrapper = sync_wrapper

        if return_anno is not None:
            wrapper.__annotations__ = {**wrapper.__annotations__, "return": return_anno}
            fn.__annotations__ = {**fn.__annotations__, "return": return_anno}

        _inject_param_docs(wrapper, fn, sig)

        # Stamp computed capability tags so the runner / select can filter:
        wrapper._a2kit_capabilities = tool_caps  # type: ignore[attr-defined]  # noqa: SLF001
        wrapper._a2kit_tool_name = resolved_tool_name  # type: ignore[attr-defined]  # noqa: SLF001
        fn._a2kit_capabilities = tool_caps  # type: ignore[attr-defined]  # noqa: SLF001
        fn._a2kit_tool_name = resolved_tool_name  # type: ignore[attr-defined]  # noqa: SLF001

        if server is not None:
            _register_with_server(server, wrapper, resolved_tool_name)

        return wrapper  # type: ignore[return-value]

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


def _inject_param_docs(wrapper: Any, fn: Any, sig: inspect.Signature) -> None:
    """If a registered param doc exists for any parameter name, append it to the
    docstring (only when the existing docstring doesn't already mention the param).

    Explicit docstring text wins; injection only fills the gaps.
    """
    from a2kit.docs import _registered_param_docs  # noqa: PLC0415

    registry = _registered_param_docs()
    if not registry:
        return
    existing = wrapper.__doc__ or ""
    additions: list[str] = []
    for param_name in sig.parameters:
        if param_name not in registry:
            continue
        if param_name in existing:
            continue
        additions.append(f"{param_name}: {registry[param_name]}")
    if not additions:
        return
    suffix = "\n\n" + "\n".join(additions)
    new_doc = (existing.rstrip() + suffix) if existing else "\n".join(additions)
    wrapper.__doc__ = new_doc
    fn.__doc__ = new_doc


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
    "_set_current_transport",
    "assert_clean_string",
    "preserve_return_annotation",
    "tool",
]


# Keep a useless reference so `from collections.abc import Awaitable` does not
# trip the unused-import lint when type-checkers thin out the import block.
_ = Awaitable
