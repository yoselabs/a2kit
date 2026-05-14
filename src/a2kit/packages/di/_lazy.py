"""``Lazy[T]`` annotation for conditional dependency injection.

A parameter typed ``Lazy[T]`` receives a zero-arg async callable that,
when awaited, resolves ``T`` through the current scope's resolver and
records cleanup. If the callable is never awaited, ``T`` is never
constructed and its ``__aenter__`` never runs — solving the
"five-resource tool only uses one" problem without service-locator
``ctx.get(T)`` antipatterns.

The alias is intentionally a public ``Callable`` shape so type
checkers see exactly what the tool body gets at runtime.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias, TypeVar

T = TypeVar("T")

# A2K019: dispatcher inspects this exact alias on tool params to wire
# the deferred closure. The protocol is the runtime shape: a zero-arg
# async callable returning T.
Lazy: TypeAlias = Callable[[], Awaitable[T]]


__all__ = ["Lazy"]
