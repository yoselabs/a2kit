"""Per-Router ContextVar accessor for the resolved `ConnectionInfo`.

# Author seam:
# Each `Router` subclass gets its own `cls.context: _RouterContext[ConnT]` ClassVar
# (see `Router.__init_subclass__`). Inside a tool decorated with
# `@MyRouter.read/.write/.tool` and `connection_param=`, the fat decorator
# sets the ContextVar to the resolved info; tools read it via
# `MyRouter.context.info()` for typed access without an `info=` kwarg.

The old `*, info: ConnT` kwarg style continues to work — both APIs run in
parallel.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Generic, TypeVar, cast

if TYPE_CHECKING:
    from a2kit.connections import ConnectionInfo

ConnT = TypeVar("ConnT", bound="ConnectionInfo")


class _RouterContext(Generic[ConnT]):
    """Typed ContextVar wrapper — one instance per Router subclass."""

    def __init__(self, router_name: str) -> None:
        self._router_name = router_name
        self._info_var: ContextVar[ConnectionInfo | None] = ContextVar(f"_a2kit_info_{router_name}", default=None)

    def info(self) -> ConnT:
        """Return the resolved `ConnectionInfo` for the active tool call.

        Raises `RuntimeError` if called outside an active tool — i.e. without
        `connection_param=` set on the decorator.
        """
        v = self._info_var.get()
        if v is None:
            msg = (
                f"a2kit context.info() called outside an active tool on router "
                f"{self._router_name!r} — wrap your function in @Router.read/.write/.tool "
                f"with `connection_param=` set."
            )
            raise RuntimeError(msg)
        return cast("ConnT", v)

    def _set(self, value: ConnectionInfo) -> Token[ConnectionInfo | None]:
        """Internal — set the ContextVar; returns a reset token."""
        return self._info_var.set(value)

    def _reset(self, token: Token[ConnectionInfo | None]) -> None:
        """Internal — restore the previous ContextVar value."""
        self._info_var.reset(token)


__all__ = ["_RouterContext"]
