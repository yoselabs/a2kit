"""MCP dispatch adapter — the per-tool error-render stage and FastMCP signature install.

The five transport-neutral dispatch concerns plus neutral error-capture
live in :mod:`a2kit.packages.dispatch`; ``build_mcp_server`` folds that
shared pipeline. This module holds only what is genuinely MCP-specific:
rendering a captured error as a ``ToolError`` envelope, and rewriting a
tool's ``__signature__`` so FastMCP introspects the agent-facing wire
params (and injects ``ctx``).
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
from typing import Any

from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult

from a2kit.packages.dispatch import (
    SYNTHESIZED_CTX_PARAM_NAME,
    CapturedError,
    close_render_state,
    get_rendered_error,
    open_render_state,
)

_log = logging.getLogger(__name__)
_WARN_ONCE: set[str] = set()


class _TypedErrorToolResult(ToolResult):
    """ToolResult that converts to ``CallToolResult(isError=True)``."""

    def to_mcp_result(self) -> Any:
        from mcp.types import CallToolResult

        return CallToolResult(
            content=self.content,
            structuredContent=self.structured_content,
            isError=True,
        )


class TypedErrorEnvelopeMiddleware(Middleware):
    """Patch ``structured_content`` onto error results from typed AppErrors.

    Pairs with :class:`McpErrorRenderStage`: that stage looks up the
    rendered envelope on the per-call render-state side channel before
    raising ``ToolError(prose) from exc``. We open the side-channel slot
    around ``call_next``, catch the ToolError, recover the envelope by
    looking up the chained AppError, and return a
    ``_TypedErrorToolResult`` carrying prose in content +
    ``{"error": envelope}`` in structured_content + isError=true.
    """

    async def on_call_tool(self, context: Any, call_next: Any) -> Any:
        from a2effect import AppError
        from fastmcp.exceptions import ToolError
        from mcp.types import TextContent

        token = open_render_state()
        try:
            try:
                return await call_next(context)
            except ToolError as te:
                cause = te.__cause__
                if not isinstance(cause, AppError):
                    raise
                rendered = get_rendered_error(cause)
                envelope = rendered.envelope if rendered is not None else cause.to_envelope_dict()
                return _TypedErrorToolResult(
                    content=[TextContent(type="text", text=str(te))],
                    structured_content={"error": envelope},
                )
        finally:
            close_render_state(token)


class McpErrorRenderStage:
    """Render a captured tool-body error as the MCP wire envelope.

    Two paths:

    - **Typed `AppError`** (incl. `UnexpectedDefect`): emit the fixed prose
      form via `ToolError(prose)` (which becomes `content[0].text` with
      `isError=true`), AND stash the envelope dict on a per-call ContextVar
      so `TypedErrorEnvelopeMiddleware` patches `structured_content =
      {"error": envelope}` onto the resulting CallToolResult. The
      single-mode wire rule (`error-envelope-rendering`): prose for the LLM,
      envelope for machine consumers, with non-overlapping info.

    - **Author-raised `FastMCPError`** (incl. plain `ToolError`): pass
      through unwrapped so author-shaped messages are not double-encoded.

    Anything else escaping the enricher chain is `quarantine`-d to
    `UnexpectedDefect` upstream, so this stage only sees AppError or
    FastMCPError on the typed path.
    """

    name = "mcp-error-render"

    def wrap(self, fn: Any, spec: Any) -> Any:  # noqa: ARG002
        from a2effect import AppError
        from fastmcp.exceptions import FastMCPError, ToolError

        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except CapturedError as ce:
                exc = ce.original
                if isinstance(exc, FastMCPError):
                    raise exc from None
                if isinstance(exc, AppError):
                    # The render-state side channel (opened by
                    # TypedErrorEnvelopeMiddleware) carries the prose +
                    # envelope written by ErrorEnvelopeStage. The
                    # ``else`` branches are defensive fallbacks for the
                    # rare case where the middleware did not run (e.g.
                    # an integration test invoking this stage in
                    # isolation).
                    rendered = get_rendered_error(exc)
                    prose = rendered.prose if rendered is not None else str(exc)
                    raise ToolError(prose) from exc
                # Anything else escaped the enricher chain — should be
                # rare since defect quarantine wraps non-AppError as
                # UnexpectedDefect. Fall back to JSON-shaped legacy error.
                payload: dict[str, Any] = {"class": ce.class_name, "message": ce.message}
                raise ToolError(json.dumps(payload)) from exc

        return _wrapped


def install_mcp_signature(fn: Any, wrapped: Any, app: Any, meta: Any) -> Any:
    """Rewrite ``wrapped``'s signature for FastMCP schema generation.

    ``wrapped`` is the outermost folded dispatch chain; ``fn`` is the
    original tool body. FastMCP introspects ``wrapped`` — it must see
    only the agent-facing wire params (DI injectables removed,
    ``connection`` added when the chain needs it) plus a ``ctx``
    parameter so FastMCP injects the live ``Context``.
    """
    from a2kit.signature import wire_input_params

    container = app.container()
    ctx_param_name = meta.context_param_name
    wire_params, wire_scopes = wire_input_params(fn, container)
    needs_conn = "connection" in wire_scopes

    new_params: list[inspect.Parameter] = []
    for name, p in wire_params.items():
        new_params.append(
            inspect.Parameter(
                name=name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=p.default if p.default is not inspect.Parameter.empty else inspect.Parameter.empty,
                annotation=p.annotation,
            )
        )
    if needs_conn and "connection" not in wire_params:
        new_params.append(
            inspect.Parameter(
                name="connection",
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=str,
            )
        )
    _ensure_ctx_in_rewritten_signature(fn, new_params, ctx_param_name)
    _install_rewritten_signature(fn, wrapped, new_params)
    return wrapped


def _install_rewritten_signature(
    fn: Any,
    wrapped: Any,
    new_params: list[inspect.Parameter],
) -> None:
    """Set ``wrapped.__signature__`` and ``wrapped.__annotations__``.

    Mirrors ``fn``'s return type while exposing only ``new_params`` on
    the wire side. Without this, tools with structured return types
    (``list[_Item]``, Pydantic models) lose their FastMCP output-schema.
    Decoration must not raise; failure degrades to leaving the return
    type unset plus a one-shot WARN line.
    """
    ret_ann: Any = inspect.Signature.empty
    try:
        from typing import get_type_hints

        ret_ann = get_type_hints(fn).get("return", inspect.Signature.empty)
    except Exception as exc:  # noqa: BLE001 -- decoration must not raise; degrade observably
        name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
        if name not in _WARN_ONCE:
            _WARN_ONCE.add(name)
            _log.warning("install_mcp_signature: failed to resolve return annotation for %s: %s", name, exc)

    # ``__signature__`` is the PEP 362 introspection target FastMCP
    # consults; setattr keeps the type checker happy without suppression.
    setattr(  # noqa: B010
        wrapped,
        "__signature__",
        inspect.Signature(parameters=new_params, return_annotation=ret_ann),
    )
    # functools.wraps copied ``fn.__annotations__`` up the chain, which
    # may carry an ``a2kit.ToolContext`` Protocol annotation pydantic
    # cannot schema-generate. Sync ``__annotations__`` with the rewritten
    # params so pydantic / get_type_hints see the same shape.
    new_annotations: dict[str, Any] = {}
    for param in new_params:
        if param.annotation is not inspect.Parameter.empty:
            new_annotations[param.name] = param.annotation
    if ret_ann is not inspect.Signature.empty:
        new_annotations["return"] = ret_ann
    wrapped.__annotations__ = new_annotations


def _ensure_ctx_in_rewritten_signature(
    fn: Any,
    new_params: list[inspect.Parameter],
    ctx_param_name: str | None,
) -> None:
    """Append a ``ctx`` Parameter to ``new_params`` so FastMCP binds the
    live ``Context`` at call time.

    Two cases:

    1. **Tool declared ctx**: re-append the tool's original Parameter
       (preserving the consumer's chosen name) with the annotation
       swapped to ``fastmcp.Context`` — pydantic cannot schema-generate
       the ``a2kit.ToolContext`` Protocol.
    2. **Tool did NOT declare ctx**: synthesize a Parameter named
       ``_a2kit_ctx`` annotated ``fastmcp.Context``. FastMCP injects ctx
       by type; the LDD stage extracts it for ambient binding and pops
       it before the body runs.

    Raises :class:`A2KitContextBindingBroken` if the post-append
    invariant is broken.
    """
    from a2kit.exceptions import A2KitContextBindingBroken

    if ctx_param_name:
        if ctx_param_name not in {p.name for p in new_params}:
            import fastmcp

            orig_ctx_param = inspect.signature(fn).parameters[ctx_param_name]
            new_params.append(
                orig_ctx_param.replace(
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=fastmcp.Context,
                )
            )
        if ctx_param_name not in {p.name for p in new_params}:
            raise A2KitContextBindingBroken(
                fn_name=getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>")),
                ctx_param_name=ctx_param_name,
            )
        return

    # Tool did not declare ctx: synthesize one so FastMCP injects ctx
    # for ambient state binding. The body never sees this kwarg.
    if SYNTHESIZED_CTX_PARAM_NAME in {p.name for p in new_params}:
        return
    import fastmcp

    new_params.append(
        inspect.Parameter(
            name=SYNTHESIZED_CTX_PARAM_NAME,
            kind=inspect.Parameter.KEYWORD_ONLY,
            annotation=fastmcp.Context,
        )
    )


__all__ = [
    "McpErrorRenderStage",
    "install_mcp_signature",
]
