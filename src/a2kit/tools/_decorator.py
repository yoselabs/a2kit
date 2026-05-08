"""The fat `@a2kit.tool` decorator.

Composes with FastMCP's `@server.tool()`. See the package `__init__.py`
docstring for the full behaviour order.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import AsyncIterator, Callable, Iterable
from typing import TYPE_CHECKING, Any, TypeVar, cast

from opentelemetry import trace as _trace

from a2kit._otel import otel_span as _otel_span
from a2kit.di import _collect_annotated_deps, resolve_annotated_deps
from a2kit.exceptions import WriteNotAllowed
from a2kit.formatter import FormatName, ListViewMode, format_from_annotation
from a2kit.tools._connection import (
    _detect_info_param,
    _lookup_connection_async,
    _lookup_connection_sync,
    _resolve_connection_key,
    _resolve_info_strings,
    _safe_list_connection_keys,
)
from a2kit.tools._metadata import (
    _compute_tool_capabilities,
    _inject_param_docs,
    _register_with_server,
)
from a2kit.tools._runtime import (
    _check_tool_call_contamination,
    _consume_or_passthrough_async,
)
from a2kit.tools._signature import (
    _check_return_annotation,
    _listview_apply,
    _listview_extract_local,
    _listview_local_params,
    _resolve_return_annotation,
    _splice_wrapper_signature,
    _verify_passthrough_params,
)

_NOOP_TRACER = _trace.NoOpTracer()

if TYPE_CHECKING:
    from a2kit._capabilities import Capability
    from a2kit.connections import ConnectionStore
    from a2kit.enrichers import EnricherFn
    from a2kit.tokens import ResolverRegistry

F = TypeVar("F", bound=Callable[..., Any])


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
    app_dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] | None = None,
) -> Callable[[F], F]:
    """Compose with FastMCP's `@server.tool()`. See package docstring for behaviour.

    All args optional. `@a2kit.tool()` with no args behaves identically to v0.1.

    v0.3: pass `server=` to auto-register the wrapped function with FastMCP's tool
    manager. Stacking with an explicit `@server.tool()` on top still works
    (idempotent — the second registration is a no-op).
    """

    def decorator(fn: F) -> F:  # noqa: C901, PLR0915
        return_anno = _check_return_annotation(fn)
        resolved_return_anno = _resolve_return_annotation(fn, return_anno)
        precomputed_format: FormatName | None = format_from_annotation(resolved_return_anno) if resolved_return_anno is not None else None
        is_async = inspect.iscoroutinefunction(fn)
        sig = inspect.signature(fn)
        resolved_tool_name = tool_name or fn.__name__
        tool_caps = _compute_tool_capabilities(set(capabilities), write=write, tool_name=resolved_tool_name)

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

        # v0.13: collect `Annotated[T, Depends(factory)]` kwonly params (additive
        # — coexists with the v0.12 connection-aware path). Sync tools with
        # Depends params raise here: factories may be async and resolution is
        # awaited, so DI is async-only.
        annotated_deps = _collect_annotated_deps(fn)
        if annotated_deps and not is_async:
            msg = "Depends-based DI requires an async tool function"
            raise TypeError(msg)

        def _prelude(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any], tuple[str, ...] | None, Any]:  # noqa: C901
            """Run pre-call steps. Returns args/kwargs/key and a context-reset token."""
            connection_key: tuple[str, ...] | None = None
            ctx_token: Any = None

            if needs_connection_arg:
                raw = kwargs.pop("connection", None)
                if raw is None:
                    msg = f"Tool {resolved_tool_name!r} requires a `connection` argument (the saved connection key)."
                    raise TypeError(msg)
                connection_key = _resolve_connection_key(raw)
                info = _lookup_connection_sync(connection_key, store)
                info = _resolve_info_strings(info, resolver_registry)
                if write and getattr(info, "read_only", False):
                    raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                if router_context is not None:
                    ctx_token = router_context._set(info)  # noqa: SLF001
                if info_target is not None:
                    kwargs[info_target[0]] = info
            elif connection_param is not None:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                if connection_param in bound.arguments:
                    raw = bound.arguments[connection_param]
                    connection_key = _resolve_connection_key(raw)
                    info = _lookup_connection_sync(connection_key, store)
                    info = _resolve_info_strings(info, resolver_registry)
                    if write and getattr(info, "read_only", False):
                        raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                    if router_context is not None:
                        ctx_token = router_context._set(info)  # noqa: SLF001

            if tool_call_guard:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                _check_tool_call_contamination(bound, resolved_tool_name)

            return args, kwargs, connection_key, ctx_token

        async def _prelude_async(  # noqa: C901
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> tuple[tuple[Any, ...], dict[str, Any], tuple[str, ...] | None, Any]:
            """Async-first prelude — mirrors `_prelude` but awaits the
            connection lookup so the event loop stays free during TOML I/O."""
            connection_key: tuple[str, ...] | None = None
            ctx_token: Any = None

            if needs_connection_arg:
                raw = kwargs.pop("connection", None)
                if raw is None:
                    msg = f"Tool {resolved_tool_name!r} requires a `connection` argument (the saved connection key)."
                    raise TypeError(msg)
                connection_key = _resolve_connection_key(raw)
                info = await _lookup_connection_async(connection_key, store)
                info = _resolve_info_strings(info, resolver_registry)
                if write and getattr(info, "read_only", False):
                    raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                if router_context is not None:
                    ctx_token = router_context._set(info)  # noqa: SLF001
                if info_target is not None:
                    kwargs[info_target[0]] = info
            elif connection_param is not None:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                if connection_param in bound.arguments:
                    raw = bound.arguments[connection_param]
                    connection_key = _resolve_connection_key(raw)
                    info = await _lookup_connection_async(connection_key, store)
                    info = _resolve_info_strings(info, resolver_registry)
                    if write and getattr(info, "read_only", False):
                        raise WriteNotAllowed(connection_key, tool_name=resolved_tool_name)
                    if router_context is not None:
                        ctx_token = router_context._set(info)  # noqa: SLF001

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
                    # Capture call_ctx for Annotated[Depends] factories *before*
                    # prelude pops `connection`. Factories that declare
                    # `connection: str` kwonly get it forwarded.
                    depends_call_ctx = dict(kwargs) if annotated_deps else {}
                    args, kwargs, conn_key, ctx_token = await _prelude_async(args, kwargs)
                    if annotated_deps:
                        resolved = await resolve_annotated_deps(
                            annotated_deps,
                            overrides=app_dependency_overrides,
                            call_ctx=depends_call_ctx,
                        )
                        kwargs.update(resolved)
                    span_cm = (
                        _otel_span(resolved_tool_name, conn_key, write)
                        if otel
                        else _NOOP_TRACER.start_as_current_span(f"a2kit.tool.{resolved_tool_name}")
                    )
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
                    from a2kit.enrichers import apply_enricher_async  # noqa: PLC0415

                    raise (await apply_enricher_async(enricher, exc, resolved_tool_name)) from exc
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
                    span_cm = (
                        _otel_span(resolved_tool_name, conn_key, write)
                        if otel
                        else _NOOP_TRACER.start_as_current_span(f"a2kit.tool.{resolved_tool_name}")
                    )
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
                    from a2kit.enrichers import apply_enricher_sync  # noqa: PLC0415

                    raise apply_enricher_sync(enricher, exc, resolved_tool_name) from exc
                finally:
                    if ctx_token is not None and router_context is not None:
                        router_context._reset(ctx_token)  # noqa: SLF001

            wrapper = sync_wrapper

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
        hide_names: set[str] = {info_target[0]} if info_target is not None else set()
        hide_names |= set(annotated_deps)
        _splice_wrapper_signature(wrapper, fn, sig, injected, hide_names=hide_names)

        if return_anno is not None:
            wrapper.__annotations__ = {**wrapper.__annotations__, "return": return_anno}
            fn.__annotations__ = {**fn.__annotations__, "return": return_anno}

        doc_connection_param = "connection" if needs_connection_arg else connection_param
        _inject_param_docs(
            wrapper,
            fn,
            sig,
            connection_param=doc_connection_param,
            cli=cli,
            available_connections=_safe_list_connection_keys(store),
        )

        # `setattr` (rather than `wrapper._a2kit_capabilities = ...`) keeps ty
        # happy: `functools.wraps` returns a `_Wrapped[...]` whose attribute set
        # ty considers closed.
        setattr(wrapper, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(wrapper, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010
        setattr(wrapper, "_a2kit_format", precomputed_format)  # noqa: B010
        setattr(wrapper, "_a2kit_annotated_deps", annotated_deps)  # noqa: B010
        setattr(fn, "_a2kit_capabilities", tool_caps)  # noqa: B010
        setattr(fn, "_a2kit_tool_name", resolved_tool_name)  # noqa: B010
        setattr(fn, "_a2kit_format", precomputed_format)  # noqa: B010

        if server is not None:
            _register_with_server(server, wrapper, resolved_tool_name)

        return cast("F", wrapper)

    return decorator


__all__ = ["tool"]
