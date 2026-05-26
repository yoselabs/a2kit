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

from a2kit.packages.dispatch._principal_bridge import (
    current_request_principal,
    current_request_principal_seeds,
    reset_request_principal,
    set_request_principal,
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
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    LddStateStage,
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
    fastapi_reserved,
    fastmcp_reserved,
    install_substrate_signature,
    split_signature,
)
from a2kit.packages.dispatch.surface import (
    SURFACE_REGISTRY,
    DecoratorSurface,
    Surface,
    SurfaceRegistry,
)

__all__ = [
    "DISPATCH_PIPELINE",
    "SURFACE_REGISTRY",
    "SYNTHESIZED_CTX_PARAM_NAME",
    "AuthorizeGateStage",
    "CapturedError",
    "DecoratorSurface",
    "DispatchHookStage",
    "DispatchStage",
    "EnricherStage",
    "ErrorCaptureStage",
    "LddStateStage",
    "RouterLazyEnterStage",
    "SplitSignature",
    "SubstrateSignatureError",
    "Surface",
    "SurfaceRegistry",
    "TimeoutStage",
    "ToolBuildSpec",
    "_run_authorize_gate",  # noqa: A2K-PKG-INIT-PURITY
    "_unwrap_annotation",  # noqa: A2K-PKG-INIT-PURITY
    "current_request_principal",
    "current_request_principal_seeds",
    "fastapi_reserved",
    "fastmcp_reserved",
    "fold_pipeline",
    "has_injectables",
    "install_substrate_signature",
    "reset_request_principal",
    "set_request_principal",
    "split_signature",
]
