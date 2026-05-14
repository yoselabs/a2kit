"""Smoke tests for ``a2kit.packages.di._helpers``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from a2kit.packages.di._helpers import (
    enter_lifecycle,
    lazy_inner_type,
    looks_like_basesettings,
)


class _Thing:
    pass


def test_lazy_inner_type_recognizes_callable_awaitable_shape() -> None:
    assert lazy_inner_type(Callable[[], Awaitable[_Thing]]) is _Thing


def test_lazy_inner_type_returns_none_for_plain_type() -> None:
    assert lazy_inner_type(_Thing) is None


def test_looks_like_basesettings_false_on_plain_class() -> None:
    assert looks_like_basesettings(_Thing) is False


def test_looks_like_basesettings_false_on_non_class() -> None:
    assert looks_like_basesettings("not a type") is False


async def test_enter_lifecycle_passthrough_when_not_async_cm() -> None:
    instance, aexit = await enter_lifecycle(_Thing())
    assert isinstance(instance, _Thing)
    assert aexit is None


async def test_enter_lifecycle_enters_async_cm() -> None:
    entered = {"n": 0}
    exited = {"n": 0}

    class _Resource:
        async def __aenter__(self) -> _Resource:
            entered["n"] += 1
            return self

        async def __aexit__(self, *_: object) -> None:
            exited["n"] += 1

    res = _Resource()
    instance, aexit = await enter_lifecycle(res)
    assert instance is res
    assert entered["n"] == 1
    assert aexit is not None
    await aexit(None, None, None)
    assert exited["n"] == 1
