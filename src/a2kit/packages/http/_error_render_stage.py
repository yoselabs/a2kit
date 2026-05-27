"""HTTP-side error-render stage — substrate-native sibling to ``McpErrorRenderStage``.

Reads the rendered envelope from the ``_render_state`` ContextVar (populated
by ``ErrorEnvelopeStage`` during pipeline fold) via ``get_rendered_error``
and returns a ``JSONResponse`` carrying ``{"error": envelope}``. Picks the
HTTP status code from the substrate-specific ``kind -> status`` map.

The kind->status mapping is HTTP-specific (gRPC and MCP map kinds
differently), so it lives here on the substrate side, not on the shared
``RenderedError`` dataclass. The pipeline produces a transport-neutral
envelope dict; each substrate's render stage decides what status code
(or exit code, or wire envelope) that envelope becomes.

Symmetric to ``a2kit.packages.mcp._wrappers.McpErrorRenderStage``; lives in
``packages/http/`` so the dispatch pipeline never imports FastAPI/Starlette.
"""

from __future__ import annotations

import functools
from typing import Any

from a2effect import AppError
from fastapi.responses import JSONResponse

from a2kit.packages.dispatch import (
    CapturedError,
    close_render_state,
    get_rendered_error,
    open_render_state,
)

# HTTP-status fallback for AppError subclasses without explicit
# ``http_status``. Per the ``error-envelope-rendering`` spec. Substrate-
# specific by design — gRPC / MCP use different mappings; this table is
# the HTTP wire-shape authority.
_KIND_HTTP_STATUS: dict[str, int] = {
    "input": 400,
    "auth": 401,
    "policy": 403,
    "infra": 503,
    "bug": 500,
}


def http_status_for(exc: AppError) -> int:
    """Return the HTTP status for ``exc``: class override wins, else kind map, else 500."""
    override = type(exc).http_status
    if override is not None:
        return override
    return _KIND_HTTP_STATUS.get(exc.base_kind, 500)


class HttpErrorRenderStage:
    """Convert a captured tool-body exception into a FastAPI ``JSONResponse``.

    On ``CapturedError`` whose wrapped exception is an ``AppError`` (or any
    subclass, including ``UnexpectedDefect`` from defect quarantine):

    - read ``RenderedError`` from ``_render_state`` via ``get_rendered_error``
    - compute HTTP status via :func:`http_status_for`
    - return ``JSONResponse(status_code=..., content={"error": rendered.envelope})``

    Defensive fallback (``get_rendered_error`` returned ``None`` — meaning
    ``ErrorEnvelopeStage`` did not run): re-raise the original exception so
    the substrate's existing exception-handler stack covers it. This path
    is documented as defensive-only; every dispatched call SHALL run through
    ``ErrorEnvelopeStage`` and populate the side channel.

    On non-AppError captured exceptions: re-raise the original so FastAPI's
    catch-all handler quarantines it to ``UnexpectedDefect``.
    """

    name = "http-error-render"

    def wrap(self, fn: Any, spec: Any) -> Any:  # noqa: ARG002 -- spec is part of the DispatchStage protocol
        @functools.wraps(fn)
        async def _wrapped(*args: Any, **kwargs: Any) -> Any:
            # Symmetric to MCP's `TypedErrorEnvelopeMiddleware.on_call_tool`:
            # open the render-state side channel around the call so
            # `ErrorEnvelopeStage` has a place to write, then read here on
            # the way out. The token is reset whether the pipeline returned
            # normally or raised.
            token = open_render_state()
            try:
                return await fn(*args, **kwargs)
            except CapturedError as ce:
                exc = ce.original
                if not isinstance(exc, AppError):
                    raise exc from ce
                rendered = get_rendered_error(exc)
                if rendered is None:
                    # ErrorEnvelopeStage did not populate the side channel
                    # (rare — only in misconfigured pipelines / isolated
                    # stage tests). Hand off to the substrate fallback
                    # handler stack.
                    raise exc from ce
                return JSONResponse(
                    status_code=http_status_for(exc),
                    content={"error": rendered.envelope},
                )
            finally:
                close_render_state(token)

        return _wrapped


__all__ = ["HttpErrorRenderStage", "http_status_for"]
