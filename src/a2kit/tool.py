from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from a2kit._verbs import list_, read, write

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from a2kit.routers import Router

Visibility = Literal["hidden", "cli", "all"]


@dataclass(frozen=True)
class ToolDescriptor:
    """Typed introspection record for a registered tool.

    Materialized by ``App.add_router`` once per tool. ``format_hint`` is
    pre-computed from the tool's resolved return type so the CLI runtime can
    skip per-call format heuristics — see
    ``a2kit.packages.formatter.inference.infer_format_hint``.
    """

    name: str
    router: Router
    fn: Callable[..., Any]
    return_type: Any | None
    format_hint: Literal["tsv", "json", "page-tsv"]


class DispatchHook(Protocol):
    """Hook called before invoking a tool method.

    Given the tool function and the wire-supplied kwargs, return the
    kwargs to pass to ``fn``. The default identity hook returns the
    input unchanged. Apps with registered providers install a non-identity
    hook that resolves typed dependencies.
    """

    def __call__(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


def identity_dispatch_hook(
    fn: Callable[..., Any],
    wire_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Default dispatch hook — pass kwargs through unchanged."""
    del fn
    return wire_kwargs


__all__ = [
    "DispatchHook",
    "ToolDescriptor",
    "Visibility",
    "identity_dispatch_hook",
    "list_",
    "read",
    "write",
]
