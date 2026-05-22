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

from a2kit.packages.dispatch.pipeline import DISPATCH_PIPELINE, fold_pipeline
from a2kit.packages.dispatch.spec import (
    SYNTHESIZED_CTX_PARAM_NAME,
    CapturedError,
    DispatchStage,
    ToolBuildSpec,
    has_injectables,
)
from a2kit.packages.dispatch.stages import (
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    LddStateStage,
    RouterLazyEnterStage,
    TimeoutStage,
)

__all__ = [
    "DISPATCH_PIPELINE",
    "SYNTHESIZED_CTX_PARAM_NAME",
    "CapturedError",
    "DispatchHookStage",
    "DispatchStage",
    "EnricherStage",
    "ErrorCaptureStage",
    "LddStateStage",
    "RouterLazyEnterStage",
    "TimeoutStage",
    "ToolBuildSpec",
    "fold_pipeline",
    "has_injectables",
]
