"""``AppAuthRegistry`` — the accumulator bound to ``App.auth(...)``.

Mirrors the ``ApiSurface`` / ``McpSurface`` accumulator pattern: one
instance per App, ordered registration, iterable for substrate-side
filtering. ``AppRuntime.auth_registry`` exposes the materialised list
to ``build_http_app`` / ``build_mcp_server``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from a2kit.packages.auth.spec import AuthSpec, AuthTarget


class AppAuthRegistry:
    """Ordered list of :class:`AuthSpec` registrations for one App.

    Order matters on the HTTP path: multiple authentication strategies
    run in registration order, first to authenticate wins. On the MCP
    path, only the first OAuth-targeting spec is honoured (FastMCP
    accepts a single ``auth=`` provider).
    """

    def __init__(self) -> None:
        self._specs: list[AuthSpec] = []

    def add(self, spec: AuthSpec) -> None:
        self._specs.append(spec)

    def all(self) -> tuple[AuthSpec, ...]:
        return tuple(self._specs)

    def for_target(self, target: AuthTarget) -> tuple[AuthSpec, ...]:
        return tuple(s for s in self._specs if s.target == target)

    def __iter__(self) -> Iterator[AuthSpec]:
        return iter(self._specs)

    def __len__(self) -> int:
        return len(self._specs)


__all__ = ["AppAuthRegistry"]
