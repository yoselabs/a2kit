"""Scope enum for the standalone DI package.

Three scopes are recognized:

- ``SINGLETON`` — one instance per :class:`Container`, cached on the root
  container. Default for ``provide(T)``.
- ``SCOPED`` — one instance per child container (per dispatch / per call).
  Opt-in via ``provide(T, per_call=True)``.
- ``TRANSIENT`` — a fresh instance every resolution. Reserved; not exposed
  on the App surface yet.

Naming follows .NET / dishka mental model rather than FastAPI's
``Depends(yield)`` overloading. See ``design.md`` D2.
"""

from __future__ import annotations

import enum


class Scope(enum.Enum):
    """DI scope for a registered provider."""

    SINGLETON = "singleton"
    SCOPED = "scoped"
    TRANSIENT = "transient"


__all__ = ["Scope"]
