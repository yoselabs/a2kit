from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from a2kit._verbs import list_, read, write

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.packages.formatter import EncodingPlan
    from a2kit.routers import Router

Visibility = Literal["hidden", "cli", "all"]


@dataclass(frozen=True)
class ToolDescriptor:
    """Typed introspection record for a registered tool.

    Materialized by ``App.add_router`` once per tool. ``format_hint`` is
    pre-computed from the tool's resolved return type so the CLI runtime can
    skip per-call format heuristics — see
    ``a2kit.packages.formatter.inference.infer_format_hint``.

    ``encoding_plan`` is the static :class:`EncodingPlan` for the return
    type — computed once here so the MCP format-routing wrapper consults it
    per call at zero decision cost (ADR 0014). It is the structured
    counterpart of ``format_hint``: it additionally marks flat-array fields
    nested inside a ``BaseModel`` envelope.
    """

    name: str
    router: Router
    fn: Callable[..., Any]
    return_type: Any | None
    format_hint: Literal["tsv", "json", "page-tsv"]
    encoding_plan: EncodingPlan


class DispatchHook(Protocol):
    """Wire-side pre-resolution hook for a tool dispatch.

    v0.37 contract (dispatch-lifecycle-wiring): given the tool function
    and the wire-supplied kwargs, return wire-side resolved kwargs.
    The hook does NOT perform DI — the framework runs
    ``Container.resolve_params`` AFTER the hook on its output. Typical
    use: convert a wire ``connection: str`` to a typed
    ``ConnectionConfig`` instance.
    """

    def __call__(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


__all__ = [
    "DispatchHook",
    "ToolDescriptor",
    "Visibility",
    "list_",
    "read",
    "write",
]
