"""The a2kit-owned ToolContext Protocol.

`a2kit.ToolContext` names the contract for "the per-call request context."
Concrete implementations live in transport-specific modules:

- ``fastmcp.Context`` (third party) satisfies it structurally under the MCP
  transport.
- :class:`a2kit.packages.context.StderrToolContext` satisfies it
  structurally under the CLI transport.

The Protocol surface is **narrow** — only the cross-transport methods that
every implementation must provide. MCP-only methods (``sample``,
``list_resources``, ``send_notification``) intentionally stay off the base
Protocol; consumers needing them annotate ``ctx: fastmcp.Context`` directly
and pay the fastmcp import cost (they are in MCP territory anyway).

The Protocol is :func:`typing.runtime_checkable` so callers can
``isinstance(ctx, ToolContext)`` if they need to assert structural
conformance at runtime. The check is O(method-count); the lazy
``a2kit.ToolContext`` re-export keeps cold-start untouched (no fastmcp
import on bare ``import a2kit``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping


@runtime_checkable
class ToolContext(Protocol):
    """Cross-transport per-call request context contract."""

    request_id: str
    client_id: str | None

    async def log(
        self,
        message: str,
        level: str | None = ...,
        logger_name: str | None = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> None: ...

    async def debug(
        self,
        message: str,
        logger_name: str | None = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> None: ...

    async def info(
        self,
        message: str,
        logger_name: str | None = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> None: ...

    async def warning(
        self,
        message: str,
        logger_name: str | None = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> None: ...

    async def error(
        self,
        message: str,
        logger_name: str | None = ...,
        extra: Mapping[str, Any] | None = ...,
    ) -> None: ...

    async def report_progress(
        self,
        progress: float,
        total: float | None = ...,
        message: str | None = ...,
    ) -> None: ...

    async def elicit(
        self,
        message: str,
        response_type: Any = ...,
        *,
        response_title: str | None = ...,
        response_description: str | None = ...,
    ) -> Any: ...

    async def set_state(self, key: str, value: Any, *, serializable: bool = ...) -> None: ...

    async def get_state(self, key: str) -> Any: ...

    async def delete_state(self, key: str) -> None: ...


__all__ = ["ToolContext"]
