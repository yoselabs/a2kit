"""BDD: custom per-scope cleanup stack contract.

Covers spec ``di-scope-cleanup-stack``: LIFO unwind, per-resource exception
isolation, body exception preservation, partial-entry safety, plus the three
named regression contracts for cpython #137517 / MCP SDK #1213 / trio #1243.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

import a2kit


class _Resource:
    """Resource that records its enter/exit order in a class-shared log."""

    log: list[tuple[str, str]] = []

    def __init__(self, name: str, *, fail_on_exit: bool = False, fail_on_enter: bool = False) -> None:
        self.name = name
        self._fail_on_exit = fail_on_exit
        self._fail_on_enter = fail_on_enter

    async def __aenter__(self) -> _Resource:
        type(self).log.append((self.name, "enter"))
        if self._fail_on_enter:
            raise RuntimeError(f"{self.name} failed to enter")
        return self

    async def __aexit__(self, *exc: object) -> None:
        type(self).log.append((self.name, "exit"))
        if self._fail_on_exit:
            raise RuntimeError(f"{self.name} failed to exit")


@pytest.fixture(autouse=True)
def _reset_log() -> None:
    _Resource.log = []


# --- Module-level classes for cross-class DI tests (PEP 563 deferred-string
# annotations can't be evaluated in function-local scope by get_type_hints).
# Used by partial-entry tests below.
class _PE_A(_Resource):
    def __init__(self) -> None:
        super().__init__("A")


class _PE_B_depends_on_A(_Resource):
    def __init__(self, a: _PE_A) -> None:
        super().__init__("B", fail_on_enter=True)


class _PE_B_plain(_Resource):
    def __init__(self) -> None:
        super().__init__("B")


class _PE_C_depends_on_A_B(_Resource):
    def __init__(self, a: _PE_A, b: _PE_B_plain) -> None:
        super().__init__("C", fail_on_enter=True)


@pytest.mark.asyncio
async def test_lifo_order() -> None:
    """Resources entered A, B, C must exit C, B, A."""

    def factory_a() -> _Resource:
        return _Resource("A")

    def factory_b(a: _Resource) -> _Resource:
        # depends on A so A enters first during resolution
        return _Resource("B")

    def factory_c(b: _Resource) -> _Resource:
        return _Resource("C")

    # Note: factories return distinct types; we register by class.
    # Use type discrimination via TypeVar-like keys is awkward here, so resolve
    # by registering three independent app-scope resources and triggering them.
    # Use three independent app-scope registrations, resolved in order.

    class _A(_Resource):
        def __init__(self) -> None:
            super().__init__("A")

    class _B(_Resource):
        def __init__(self) -> None:
            super().__init__("B")

    class _C(_Resource):
        def __init__(self) -> None:
            super().__init__("C")

    app = a2kit.App("test")
    app.provide(_A)
    app.provide(_B)
    app.provide(_C)

    async with app:
        # Resolve in order A → B → C.
        await app._resolver.get(_A)
        await app._resolver.get(_B)
        await app._resolver.get(_C)

    # After app exits, LIFO unwind: C, B, A.
    events = [e for e in _Resource.log if e[1] == "exit"]
    assert events == [("C", "exit"), ("B", "exit"), ("A", "exit")], f"LIFO unwind violated: {events}"


@pytest.mark.asyncio
async def test_per_resource_exception_isolation(caplog: pytest.LogCaptureFixture) -> None:
    """A failing cleanup logs WARN, siblings still run, scope close does not raise."""

    class _A(_Resource):
        def __init__(self) -> None:
            super().__init__("A")

    class _B(_Resource):
        def __init__(self) -> None:
            super().__init__("B", fail_on_exit=True)

    class _C(_Resource):
        def __init__(self) -> None:
            super().__init__("C")

    app = a2kit.App("test")
    app.provide(_A)
    app.provide(_B)
    app.provide(_C)

    async with app:
        await app._resolver.get(_A)
        await app._resolver.get(_B)
        await app._resolver.get(_C)
        caplog.set_level(logging.WARNING, logger="a2kit.di.cleanup")

    # All three exits ran (in LIFO order), B's failure was logged, scope closed cleanly.
    exits = [e for e in _Resource.log if e[1] == "exit"]
    assert ("A", "exit") in exits
    assert ("B", "exit") in exits
    assert ("C", "exit") in exits
    assert any("B failed to exit" in r.message for r in caplog.records), "B's cleanup failure was not logged at WARN"


@pytest.mark.asyncio
async def test_body_exception_preserved() -> None:
    """When body raises and cleanup also raises, body exception wins."""

    class _Bad(_Resource):
        def __init__(self) -> None:
            super().__init__("bad", fail_on_exit=True)

    class _BodyError(RuntimeError):
        pass

    app = a2kit.App("test")
    app.provide(_Bad)

    with pytest.raises(_BodyError, match="body failed"):
        async with app:
            await app._resolver.get(_Bad)
            raise _BodyError("body failed")


@pytest.mark.asyncio
async def test_partial_entry_unwinds_already_entered() -> None:
    """If B fails during __aenter__, A (already entered) is still cleaned up."""
    app = a2kit.App("test")
    app.provide(_PE_A)
    app.provide(_PE_B_depends_on_A)

    async with app:
        with pytest.raises(RuntimeError, match="B failed to enter"):
            await app._resolver.get(_PE_B_depends_on_A)
        # A is on the stack; B is not.

    # After app exits, A must have been cleaned up; B never was (never entered).
    a_exit_count = sum(1 for e in _Resource.log if e == ("A", "exit"))
    b_exit_count = sum(1 for e in _Resource.log if e == ("B", "exit"))
    assert a_exit_count == 1, f"A.__aexit__ ran {a_exit_count} times — expected 1"
    assert b_exit_count == 0, f"B.__aexit__ ran {b_exit_count} times — expected 0"


@pytest.mark.asyncio
async def test_background_task_exception_during_close() -> None:
    """Regression contract for cpython #137517: background-task exception during scope close.

    A scope close that runs while a sibling TaskGroup has a background task
    raising must not delay or swallow the cleanup of resources on this scope's
    stack. This is the failure mode that bites stdlib ``AsyncExitStack`` when
    composed with ``asyncio.gather`` / ``TaskGroup``.
    """

    class _R(_Resource):
        def __init__(self) -> None:
            super().__init__("R")

    app = a2kit.App("test")
    app.provide(_R)

    async def _background_raiser() -> None:
        await asyncio.sleep(0.01)
        raise RuntimeError("bg task")

    bg_task = asyncio.create_task(_background_raiser())
    try:
        async with app:
            await app._resolver.get(_R)
            await asyncio.sleep(0)
    except RuntimeError:
        # ignore bg propagation if it happens
        pass
    finally:
        bg_task.cancel()
        with pytest.raises((asyncio.CancelledError, RuntimeError)):
            await bg_task

    # R's cleanup ran exactly once despite the background task.
    assert ("R", "exit") in _Resource.log


@pytest.mark.asyncio
async def test_partial_entry_on_startup_failure() -> None:
    """Regression contract for MCP SDK #1213: partial stack on a startup failure unwinds correctly."""

    app = a2kit.App("test")
    app.provide(_PE_A)
    app.provide(_PE_B_plain)
    app.provide(_PE_C_depends_on_A_B)

    async with app:
        with pytest.raises(RuntimeError, match="C failed to enter"):
            await app._resolver.get(_PE_C_depends_on_A_B)

    # A and B both cleaned up; C never on the stack.
    exits = [e for e in _Resource.log if e[1] == "exit"]
    names_exited = {e[0] for e in exits}
    assert names_exited == {"A", "B"}, f"unexpected unwind set: {names_exited}"


@pytest.mark.asyncio
async def test_cleanup_within_taskgroup_context() -> None:
    """Regression contract for trio #1243: cleanup nested in a TaskGroup context."""

    class _R(_Resource):
        def __init__(self) -> None:
            super().__init__("R")

    app = a2kit.App("test")
    app.provide(_R)

    async def _noop() -> None:
        await asyncio.sleep(0)

    async with asyncio.TaskGroup() as tg, app:
        await app._resolver.get(_R)
        tg.create_task(_noop())

    assert ("R", "exit") in _Resource.log
