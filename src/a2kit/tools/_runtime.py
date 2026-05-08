"""Runtime context bits: transport seam, OTel null-span, contamination guard,
async-iterator passthrough.

These are the pieces the @tool wrapper needs *during* a call (vs. signature
manipulation done at decoration time, or metadata stamping done after).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import ToolCallContamination

if TYPE_CHECKING:
    import inspect
    from collections.abc import AsyncIterator

_TRANSPORT_VAR: ContextVar[str | None] = ContextVar("a2kit_current_transport", default=None)
_TOOL_CALL_CONTAMINATION_MARKER = "<parameter name="


class _NullSpan:
    """Local no-op CM used when `otel=False` is passed to the decorator."""

    def __enter__(self) -> _NullSpan:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _set_current_transport(name: str | None) -> None:
    """Internal seam used by `MCPRunner` (and tests) to flag transport.

    v0.11: backed by `ContextVar` (was `threading.local`) for consistency
    with `_RouterContext` and correctness under multi-worker async schedulers.
    """
    _TRANSPORT_VAR.set(name)


def _get_current_transport() -> str:
    """Return current transport name; defaults to `'stdio'`."""
    return _TRANSPORT_VAR.get() or "stdio"


def assert_clean_string(value: str, param_name: str = "<unnamed>", tool_name: str | None = None) -> None:
    """Raise `ToolCallContamination` if `value` contains a tool-call envelope tag.

    Exposed standalone so consumers can run the same check in helper functions
    that don't go through the decorator.
    """
    if isinstance(value, str) and _TOOL_CALL_CONTAMINATION_MARKER in value:
        raise ToolCallContamination(param_name=param_name, tool_name=tool_name)


def _check_tool_call_contamination(bound: inspect.BoundArguments, fn_name: str) -> None:
    for name, value in bound.arguments.items():
        if isinstance(value, str):
            assert_clean_string(value, param_name=name, tool_name=fn_name)


async def _consume_or_passthrough_async(async_iter: AsyncIterator[Any]) -> Any:
    """If transport is stdio, collect into a list. Otherwise pass through."""
    if _get_current_transport() == "stdio":
        return [item async for item in async_iter]
    return async_iter


__all__ = [
    "_TOOL_CALL_CONTAMINATION_MARKER",
    "_NullSpan",
    "_check_tool_call_contamination",
    "_consume_or_passthrough_async",
    "_get_current_transport",
    "_set_current_transport",
    "assert_clean_string",
]
