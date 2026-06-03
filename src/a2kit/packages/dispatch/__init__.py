"""Transport-neutral per-tool dispatch pipeline — shared by the CLI and MCP adapters.

The five transport-neutral dispatch concerns (timeout, enrichers,
router-lazy-enter, dispatch-hook + DI, LDD ambient) plus neutral
error-capture live here as :class:`DispatchStage` objects. Both the CLI
and MCP adapters fold the single :data:`DISPATCH_PIPELINE`; each then
appends its own per-transport error-RENDER stage. This package MUST NOT
import ``fastmcp`` — the CLI consumer folds the same pipeline and cannot
afford the cold-start cost.
"""

from __future__ import annotations

from a2kit.packages.context import request_scope
from a2kit.packages.dispatch._render_state import (
    RenderedError,
    close_render_state,
    get_rendered_error,
    open_render_state,
    set_rendered_error,
)
from a2kit.packages.dispatch.pipeline import DISPATCH_PIPELINE, fold_pipeline
from a2kit.packages.dispatch.spec import (
    SYNTHESIZED_CTX_PARAM_NAME,
    CapturedError,
    DispatchStage,
    ToolBuildSpec,
    has_injectables,
)

# GRANDFATHERED: `_run_authorize_gate` is re-exported for test + sibling-stage
# use; remove from __all__ when a refactor makes the symbol fully internal.
from a2kit.packages.dispatch.stages import (  # noqa: A2K-PKG-INIT-PURITY
    AuthorizeGateStage,
    CallLogStage,
    CallScopeStage,
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    RouterLazyEnterStage,
    TimeoutStage,
    _run_authorize_gate,
)

# GRANDFATHERED: `_unwrap_annotation` is re-exported for signature plumbing;
# remove from __all__ when a refactor makes it fully internal.
from a2kit.packages.dispatch.substrate import (  # noqa: A2K-PKG-INIT-PURITY
    SplitSignature,
    SubstrateSignatureError,
    _unwrap_annotation,
    fastapi_dep_markers,
    fastapi_reserved,
    fastmcp_reserved,
    install_substrate_signature,
    split_signature,
)
from a2kit.packages.dispatch.surface import (
    DecoratorSurface,
    Surface,
    SurfaceRegistry,
)

__all__ = [
    "DISPATCH_PIPELINE",
    "SYNTHESIZED_CTX_PARAM_NAME",
    "AuthorizeGateStage",
    "CallLogStage",
    "CallScopeStage",
    "CapturedError",
    "DecoratorSurface",
    "DispatchHookStage",
    "DispatchStage",
    "EnricherStage",
    "ErrorCaptureStage",
    "RenderedError",
    "RouterLazyEnterStage",
    "SplitSignature",
    "SubstrateSignatureError",
    "Surface",
    "SurfaceRegistry",
    "TimeoutStage",
    "ToolBuildSpec",
    "_run_authorize_gate",  # noqa: A2K-PKG-INIT-PURITY
    "_unwrap_annotation",  # noqa: A2K-PKG-INIT-PURITY
    "close_render_state",
    "fastapi_dep_markers",
    "fastapi_reserved",
    "fastmcp_reserved",
    "fold_pipeline",
    "get_rendered_error",
    "has_injectables",
    "install_substrate_signature",
    "open_render_state",
    "request_scope",
    "set_rendered_error",
    "split_signature",
]
