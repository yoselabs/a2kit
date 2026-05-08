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
from a2kit.connections import ConnectionInfo
from a2kit.di import _collect_annotated_deps, _factory_non_depends_kwonly, resolve_annotated_deps
from a2kit.formatter import FormatName, ListViewMode, format_from_annotation
from a2kit.middleware._chain import Middleware, ToolContext, _build_chain, compose
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
    from a2kit.enrichers import EnricherFn

F = TypeVar("F", bound=Callable[..., Any])


def tool(  # noqa: C901, PLR0915 — fat decorator by design
    *,
    enricher: EnricherFn | None = None,
    write: bool = False,
    streaming: bool = False,
    tool_call_guard: bool = True,
    otel: bool = True,
    bare: bool = False,
    middleware: list[Middleware] | None = None,
    router_middleware: list[Middleware] | None = None,
    app_middleware: list[Middleware] | None = None,
    tool_name: str | None = None,
    server: Any = None,
    capabilities: Iterable[Capability] = (),
    filter: ListViewMode | None = None,  # noqa: A002
    fields: ListViewMode | None = None,
    pagination: ListViewMode | None = None,
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

        # v0.15: Annotated[T, Depends(factory)] is the only DI path.
        # Sync tools with Depends params raise here: factories may be async
        # and resolution is awaited, so DI is async-only.
        annotated_deps = _collect_annotated_deps(fn)
        if annotated_deps and not is_async:
            msg = "Depends-based DI requires an async tool function"
            raise TypeError(msg)

        def _prelude(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
            """Sync-tool prelude — only runs tool_call_guard."""
            if tool_call_guard:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                _check_tool_call_contamination(bound, resolved_tool_name)
            return args, kwargs

        async def _prelude_async(
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
        ) -> tuple[tuple[Any, ...], dict[str, Any]]:
            """Async-tool prelude — only runs tool_call_guard.

            Connection loading and ConnectionInfo lifting are the job of
            `Annotated[T, Depends(factory)]` resolution downstream; the
            decorator no longer owns connection vocabulary.
            """
            if tool_call_guard:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                _check_tool_call_contamination(bound, resolved_tool_name)
            return args, kwargs

        # ── Implicit middleware chain (v0.13) ──
        # Built once at decoration time and reused for every call. The chain
        # wraps the inner fn body; prelude (connection load + router_context
        # push) and Annotated[Depends] resolution run before the chain so
        # tool_call_guard sees the cleaned kwargs.
        _verb_from_listview = "list" if has_listview and (filter is not None and fields is not None and pagination is not None) else "tool"
        _chain: list[Middleware] = _build_chain(
            verb=_verb_from_listview,  # type: ignore[arg-type]
            write=write,
            has_listview=has_listview,
            enricher=enricher,
            router_middleware=router_middleware,
            app_middleware=app_middleware,
            otel=otel,
            tool_call_guard_on=bool(tool_call_guard),
            bare=bare,
            extra_pre=list(middleware) if middleware else None,
        )
        _tool_caps_frozen = frozenset(tool_caps)
        _lv_settings: dict[str, Any] = {
            "filter": filter,
            "fields": fields,
            "pagination": pagination,
            "format": precomputed_format,
        }

        if is_async:

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: C901
                try:
                    # Extract listview kwargs *before* anything else so the
                    # chain (esp. tool_call_guard's bind_partial) never sees
                    # injected kit params (filter / fields / cursor / limit).
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
                    # Capture call_ctx for Annotated[Depends] factories *before*
                    # we pop `connection` from kwargs. Factories that declare
                    # `connection: str` kwonly get it forwarded.
                    depends_call_ctx = dict(kwargs) if annotated_deps else {}
                    # Pop `connection` before prelude — tool_call_guard's
                    # bind_partial would otherwise complain about a kwarg the
                    # inner fn never declared.
                    if deps_need_connection:
                        kwargs.pop("connection", None)
                    args, kwargs = await _prelude_async(args, kwargs)
                    loaded_conn: Any = None
                    if annotated_deps:
                        resolved = await resolve_annotated_deps(
                            annotated_deps,
                            overrides=app_dependency_overrides,
                            call_ctx=depends_call_ctx,
                        )
                        kwargs.update(resolved)
                        # Lift the first ConnectionInfo-typed resolved value
                        # into ctx.state for downstream middleware
                        # (e.g. WriteEnforce). Cheap: dict iteration.
                        for v in resolved.values():
                            if isinstance(v, ConnectionInfo):
                                loaded_conn = v
                                break
                    conn_key = depends_call_ctx.get("connection") if loaded_conn is not None else None

                    # Bind positional args into kwargs so the chain (kwargs-only)
                    # forwards them through. Skip injected listview / connection
                    # params that aren't part of the inner fn signature.
                    if args:
                        # Only bind real parameters of the inner fn — leave
                        # injected kit params (filter/fields/cursor/limit) in
                        # kwargs as-is so the listview middleware can extract.
                        sig_param_names = set(sig.parameters)
                        passthrough = {k: v for k, v in kwargs.items() if k not in sig_param_names}
                        bind_kwargs = {k: v for k, v in kwargs.items() if k in sig_param_names}
                        bound = sig.bind_partial(*args, **bind_kwargs)
                        bound.apply_defaults()
                        kwargs = {**dict(bound.arguments), **passthrough}

                    ctx = ToolContext(
                        tool_name=resolved_tool_name,
                        verb=_verb_from_listview,  # type: ignore[arg-type]
                        write=write,
                        capabilities=_tool_caps_frozen,
                        format_hint=precomputed_format,
                        state={
                            "connection_key": conn_key,
                            "loaded_conn": loaded_conn,
                            "sig": sig,
                            "lv_settings": _lv_settings,
                            "lv_state": lv_state,
                            "streaming": streaming,
                        },
                    )

                    async def _inner(**kw: Any) -> Any:
                        return await fn(**kw)

                    if not _chain:
                        # bare=True path — call inner directly.
                        result = await _inner(**kwargs)
                    else:
                        handler = compose(_chain, _inner, ctx)
                        result = await handler(**kwargs)
                    # Streaming drain for the non-listview path. The listview
                    # middleware drains when present; here we cover the
                    # streaming=True + no-listview case.
                    if streaming and isinstance(result, AsyncIterator):
                        return await _consume_or_passthrough_async(result)
                    return result
                except Exception as exc:
                    # Prelude exceptions land here (the chain's enrich middleware
                    # only sees post-prelude exceptions). Apply the enricher to
                    # *any* exception so Depends-factory failures still get
                    # enriched.
                    if enricher is None or bare:
                        raise
                    from a2kit.enrichers import apply_enricher_async  # noqa: PLC0415

                    raise (await apply_enricher_async(enricher, exc, resolved_tool_name)) from exc

            wrapper: Callable[..., Any] = async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
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
                    args, kwargs = _prelude(args, kwargs)
                    span_cm = (
                        _otel_span(resolved_tool_name, None, write)
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

            wrapper = sync_wrapper

        injected: list[inspect.Parameter] = []

        # When Annotated[..., Depends(factory)] params declare a
        # `connection: str` kwonly on the factory side, expose `connection`
        # as a wrapper kwarg so callers (FastMCP, Click subcommands, direct
        # invocation) can pass it. The resolver forwards it as call_ctx.
        def _walk_factory_needs_connection(factory: Any, seen: set[Any]) -> bool:
            """Walk transitively: does this factory (or any of its Depends factories) declare `connection`?"""
            if factory in seen:
                return False
            seen.add(factory)
            if "connection" in _factory_non_depends_kwonly(factory):
                return True
            return any(_walk_factory_needs_connection(d.dependency, seen) for d in _collect_annotated_deps(factory).values())

        deps_need_connection = any(_walk_factory_needs_connection(d.dependency, set()) for d in annotated_deps.values())
        if deps_need_connection:
            injected.append(
                inspect.Parameter(
                    "connection",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=inspect.Parameter.empty,
                    annotation=str,
                )
            )
        injected.extend(_listview_local_params(filter_mode=filter, fields_mode=fields, pagination_mode=pagination))
        hide_names: set[str] = set(annotated_deps)
        _splice_wrapper_signature(wrapper, fn, sig, injected, hide_names=hide_names)

        if return_anno is not None:
            wrapper.__annotations__ = {**wrapper.__annotations__, "return": return_anno}
            fn.__annotations__ = {**fn.__annotations__, "return": return_anno}

        doc_connection_param = "connection" if deps_need_connection else None
        _inject_param_docs(
            wrapper,
            fn,
            sig,
            connection_param=doc_connection_param,
            cli=cli,
            available_connections=None,
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
