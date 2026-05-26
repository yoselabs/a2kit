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
from a2kit.packages.dispatch.stages import (
    AuthorizeGateStage,
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    LddStateStage,
    RouterLazyEnterStage,
    TimeoutStage,
    _run_authorize_gate,
)
from a2kit.packages.dispatch.substrate import (
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
    "_run_authorize_gate",
    "_unwrap_annotation",
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
