"""The canonical dispatch pipeline and its fold helper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2kit.packages.dispatch.envelope import ErrorEnvelopeStage
from a2kit.packages.dispatch.stages import (
    AuthorizeGateStage,
    CallLogStage,
    CallScopeStage,
    DispatchHookStage,
    EnricherStage,
    ErrorCaptureStage,
    RouterLazyEnterStage,
    TimeoutStage,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.dispatch.spec import DispatchStage, ToolBuildSpec

#: The per-tool dispatch chain, innermost-first. Folding it onto a tool
#: body wraps it so, from the body outward: the timeout cancel scope
#: covers only the bare body; the router's enrichers translate its
#: exceptions; the router enters lazily on first touch; the dispatch
#: hook + per-call DI scope resolve kwargs; the call scope (ctx + minted
#: call_id) is bound; the call-log captures the access record; tool-body
#: exceptions are captured into a neutral ``CapturedError``.
#:
#: Order rationale: timeout is innermost so DI resolution and scope setup
#: are not charged against the budget; ``CallScopeStage`` is outer of
#: ``CallLogStage`` so the call-log sees the minted ``call_id`` and the wire
#: args (pre-DI); error-capture is outermost so it sees every other stage's
#: exceptions. Each transport adapter folds this exact tuple, then appends
#: its own error-RENDER stage.
DISPATCH_PIPELINE: tuple[DispatchStage, ...] = (
    TimeoutStage(),
    EnricherStage(),
    ErrorEnvelopeStage(),
    RouterLazyEnterStage(),
    DispatchHookStage(),
    AuthorizeGateStage(),
    CallLogStage(),
    CallScopeStage(),
    ErrorCaptureStage(),
)


def fold_pipeline(
    fn: Callable[..., Any],
    spec: ToolBuildSpec,
    pipeline: tuple[DispatchStage, ...] = DISPATCH_PIPELINE,
) -> Callable[..., Any]:
    """Fold ``pipeline`` onto ``fn``.

    Each stage wraps the running result in tuple order, so the first
    stage ends up innermost (closest to ``fn``) and the last outermost.
    A stage that self-skips returns its input unchanged, so the fold
    silently drops inapplicable concerns without reordering.
    """
    wrapped = fn
    for stage in pipeline:
        wrapped = stage.wrap(wrapped, spec)
    return wrapped


__all__ = ["DISPATCH_PIPELINE", "fold_pipeline"]
