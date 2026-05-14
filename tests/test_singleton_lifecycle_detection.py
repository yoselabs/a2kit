"""BDD contract for consolidate-lifecycle-on-async-cm-protocol task 1.3.

Framework auto-detects singleton cleanup protocol in order:
1. ``__aexit__`` (paired with ``__aenter__``)
2. ``aclose()``
3. ``close()``  (sync or async)
4. None — no teardown registered, no error
"""

from __future__ import annotations

import pytest

import a2kit

pytestmark = pytest.mark.skip(reason="contract for consolidate-lifecycle-on-async-cm-protocol; un-skip when impl lands")


@pytest.mark.asyncio
async def test_aexit_protocol_detected() -> None:
    entered: list[bool] = []
    exited: list[bool] = []

    class _R:
        async def __aenter__(self) -> _R:
            entered.append(True)
            return self

        async def __aexit__(self, *_exc: object) -> None:
            exited.append(True)

    app = a2kit.App("x")
    app.singleton(_R)
    async with app:
        pass
    assert entered == [True]
    assert exited == [True]


@pytest.mark.asyncio
async def test_aclose_method_detected_when_no_aexit() -> None:
    closed: list[bool] = []

    class _R:
        async def aclose(self) -> None:
            closed.append(True)

    app = a2kit.App("x")
    app.singleton(_R)
    async with app:
        pass
    assert closed == [True]


@pytest.mark.asyncio
async def test_sync_close_method_detected_when_no_async_path() -> None:
    closed: list[bool] = []

    class _R:
        def close(self) -> None:
            closed.append(True)

    app = a2kit.App("x")
    app.singleton(_R)
    async with app:
        pass
    assert closed == [True]


@pytest.mark.asyncio
async def test_no_cleanup_protocol_is_fine() -> None:
    class _R:
        pass

    app = a2kit.App("x")
    app.singleton(_R)
    # Must not raise — no teardown is a valid state.
    async with app:
        pass


@pytest.mark.asyncio
async def test_teardown_kwarg_raises_with_hint() -> None:
    class _R:
        def close(self) -> None: ...

    app = a2kit.App("x")
    with pytest.raises(TypeError) as ei:
        app.singleton(_R, teardown=lambda r: r.close())  # type: ignore[call-arg]
    msg = str(ei.value)
    assert "teardown=" in msg
    assert "__aexit__" in msg
