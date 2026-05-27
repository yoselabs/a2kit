"""Mirror tests for packages/dispatch/_invoke — canonical `_call` helper.

The shared `_call` consolidates R1 from the 2026-05-27 structural audit
(the two identical `_call` definitions across `envelope.py` and
`stages.py`). End-to-end use is covered by the dispatch pipeline tests.
"""

from __future__ import annotations

import pytest

from a2kit.packages.dispatch._invoke import _call


async def _sync_fn(x: int) -> int:
    return x * 2


async def _async_fn(x: int) -> int:
    return x + 10


def _plain_sync(x: int) -> int:
    return x - 1


@pytest.mark.asyncio
async def test_call_invokes_sync_callable_and_returns_value():
    assert await _call(_plain_sync, 5) == 4


@pytest.mark.asyncio
async def test_call_awaits_coroutine_result():
    assert await _call(_async_fn, 5) == 15


@pytest.mark.asyncio
async def test_call_awaits_async_def_returning_coroutine():
    assert await _call(_sync_fn, 5) == 10


@pytest.mark.asyncio
async def test_call_passes_args_and_kwargs():
    def fn(a: int, b: int, *, c: int) -> int:
        return a + b + c

    assert await _call(fn, 1, 2, c=3) == 6
