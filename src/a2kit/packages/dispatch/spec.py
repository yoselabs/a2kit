"""Dispatch build-spec, the stage protocol, and the neutral error-capture type."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.metadata import A2KitMeta
    from a2kit.routers import Router
    from a2kit.runtime import AppRuntime

#: Framework-reserved parameter name synthesized into an MCP tool's
#: rewritten signature when its body does not declare ``ctx`` — FastMCP
#: injects ctx by type under this name so ambient binding is always
#: available. Tool bodies never see it; the LDD stage pops it. The CLI
#: adapter does not use it (it synthesizes a ``StderrToolContext``
#: directly), but the constant is transport-neutral so it lives here.
SYNTHESIZED_CTX_PARAM_NAME = "_a2kit_ctx"


@dataclass(frozen=True)
class ToolBuildSpec:
    """Everything a dispatch stage needs to wrap one tool.

    Transport-neutral: the MCP adapter builds one per tool at
    server-build time; the CLI adapter builds one per invocation.
    """

    app: AppRuntime
    router: Router | None
    meta: A2KitMeta | None
    reports_enabled: bool = True
    events_enabled: bool = True
    sinks: tuple[Any, ...] = ()


@runtime_checkable
class DispatchStage(Protocol):
    """One concern in the per-tool dispatch chain.

    ``wrap`` returns a callable that wraps ``fn`` with the stage's
    behaviour, or ``fn`` itself unchanged when the concern does not
    apply to this tool (the self-skip rule). Stages MUST NOT be
    filtered or reordered per tool — a conditional stage self-skips.
    """

    name: str

    def wrap(self, fn: Callable[..., Any], spec: ToolBuildSpec) -> Callable[..., Any]:
        """Return ``fn`` wrapped with this stage, or ``fn`` unchanged."""
        ...


class CapturedError(Exception):
    """Neutral capture of a tool-body exception.

    Raised by :class:`~a2kit.packages.dispatch.stages.ErrorCaptureStage`
    in place of the original. The outermost per-transport render stage
    converts it to a wire shape — a ``ToolError`` JSON envelope for MCP,
    an exit code for the CLI. Carries the original exception plus its
    class name, message, and formatted traceback, all snapshotted at
    capture time so the render stage need not be inside the ``except``.
    """

    def __init__(self, original: BaseException) -> None:
        self.original = original
        self.class_name = type(original).__name__
        self.message = str(original)
        self.traceback_str = "".join(traceback.format_exception(type(original), original, original.__traceback__))
        super().__init__(self.message)


def has_injectables(fn: Callable[..., Any], container: Any) -> bool:
    """True when ``fn`` declares a DI-resolvable parameter.

    Compares the wire-param set with and without the container: any
    shrinkage (or a wire-scope requirement, e.g. ``connection``) means
    there is something for the dispatch hook + DI to resolve. When this
    is false and the App carries the default identity hook,
    ``DispatchHookStage`` self-skips.
    """
    if container is None:
        return False
    from a2kit.signature import wire_input_params

    base, _ = wire_input_params(fn, container=None)
    wire, wire_scopes = wire_input_params(fn, container=container)
    return len(wire) < len(base) or bool(wire_scopes)


__all__ = [
    "SYNTHESIZED_CTX_PARAM_NAME",
    "CapturedError",
    "DispatchStage",
    "ToolBuildSpec",
    "has_injectables",
]
