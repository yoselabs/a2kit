"""BDD scenarios for ``a2kit.testing.lazy``.

The helper wraps a pre-built value into the ``Lazy[T]`` shape
(``Callable[[], Awaitable[T]]``) used at the tool seam. Five-line
helper that every consumer would otherwise reinvent in conftest —
shipped per a2web round-10 feedback Friction A1.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

import pytest

from a2kit.testing import lazy


@pytest.mark.asyncio
async def test_lazy_returns_zero_arg_async_callable() -> None:
    """``lazy(v)`` returns a callable awaitable with no arguments."""
    sentinel = object()

    thunk = lazy(sentinel)

    assert callable(thunk)
    sig = inspect.signature(thunk)
    assert len(sig.parameters) == 0
    result = thunk()
    assert inspect.isawaitable(result)
    awaited = await result
    assert awaited is sentinel


@pytest.mark.asyncio
async def test_lazy_preserves_identity_across_calls() -> None:
    """Awaiting the thunk multiple times yields the original value
    by identity — no copy, no caching wrapper."""
    sentinel = object()
    thunk = lazy(sentinel)

    first = await thunk()
    second = await thunk()

    assert first is sentinel
    assert second is sentinel
    assert first is second


@pytest.mark.asyncio
async def test_lazy_satisfies_lazy_type_alias_shape() -> None:
    """The returned callable matches the structural shape of
    ``Lazy[T] = Callable[[], Awaitable[T]]`` declared at
    ``packages/di/_lazy.py``. We can't isinstance-check a TypeAlias,
    so we structurally verify the contract a tool-seam unwrap would
    rely on."""
    value = 42

    thunk: Callable[[], Awaitable[int]] = lazy(value)

    awaited = await thunk()
    assert awaited == 42


@pytest.mark.asyncio
async def test_lazy_wraps_none_value() -> None:
    """``lazy(None)`` is a valid call and the thunk returns ``None``.
    Distinguishes value-None (legitimate) from missing-thunk."""
    thunk = lazy(None)
    assert await thunk() is None


@pytest.mark.asyncio
async def test_lazy_wraps_complex_value() -> None:
    """Identity and shape preserved for dataclass-ish values."""

    class Fake:
        def __init__(self, name: str) -> None:
            self.name = name

    instance = Fake(name="resource")
    thunk = lazy(instance)

    awaited = await thunk()
    assert awaited is instance
    assert awaited.name == "resource"
