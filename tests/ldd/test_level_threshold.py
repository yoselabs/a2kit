"""BDD tests for the LDD level-threshold filter (ldd-log-level change).

Locks the ldd-level-threshold capability:
- Level vocab and rank mapping are stable and exported
- Emissions below the configured threshold are dropped before any sink
  fan-out, ctx.log call, or stderr emit
- The threshold is stamped on per-call ambient state at dispatch entry
- The events_enabled kill-switch is orthogonal (hard-off)
- event() / report() respect explicit level=
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import anyio
import pytest

import a2kit
from a2kit.ldd import (
    LDD_LEVEL_RANK,
    debug as ldd_debug,
    error as ldd_error,
    event as ldd_event,
    info as ldd_info,
    ldd_state_for_call,
    log as ldd_log,
    report as ldd_report,
    warning as ldd_warning,
)
from a2kit.packages.context import StderrToolContext
from a2kit.packages.ldd import LddEmission


@pytest.fixture(autouse=True)
def _clear_a2kit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for k in list(os.environ):
        if k.startswith("A2KIT_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture
def no_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ----- Vocabulary + ranks ------------------------------------------------ #


def test_rank_mapping_is_fixed() -> None:
    assert LDD_LEVEL_RANK == {"trace": 10, "debug": 20, "info": 30, "warning": 40, "error": 50}


def test_ranks_order_levels_low_to_high() -> None:
    assert LDD_LEVEL_RANK["trace"] < LDD_LEVEL_RANK["debug"]
    assert LDD_LEVEL_RANK["debug"] < LDD_LEVEL_RANK["info"]
    assert LDD_LEVEL_RANK["info"] < LDD_LEVEL_RANK["warning"]
    assert LDD_LEVEL_RANK["warning"] < LDD_LEVEL_RANK["error"]


# ----- Filter at the primitive ------------------------------------------ #


def _drain(*, threshold: int, calls: list[tuple]) -> tuple:
    """Helper: bind ambient with the given threshold, fire one of every level via log()."""

    async def sink(e: LddEmission) -> None:
        calls.append((e.kind, e.name))

    async def run() -> None:
        ctx = StderrToolContext()
        with ldd_state_for_call(ctx=ctx, sinks=(sink,), level_threshold=threshold):
            await ldd_log("trace", "t-msg")
            await ldd_debug("d-msg")
            await ldd_info("i-msg")
            await ldd_warning("w-msg")
            await ldd_error("e-msg")

    anyio.run(run)
    return tuple(name for _kind, name in calls)


def test_default_threshold_zero_lets_everything_through() -> None:
    """When threshold is 0 (sentinel for 'no filtering'), all levels pass.

    This is the fixture-default behaviour — tests that don't set a
    threshold still observe every emission.
    """
    calls: list[tuple] = []
    seen = _drain(threshold=0, calls=calls)
    assert seen == ("t-msg", "d-msg", "i-msg", "w-msg", "e-msg")


def test_info_threshold_drops_debug_and_trace() -> None:
    calls: list[tuple] = []
    seen = _drain(threshold=LDD_LEVEL_RANK["info"], calls=calls)
    assert seen == ("i-msg", "w-msg", "e-msg")


def test_trace_threshold_lets_everything_through() -> None:
    calls: list[tuple] = []
    seen = _drain(threshold=LDD_LEVEL_RANK["trace"], calls=calls)
    assert seen == ("t-msg", "d-msg", "i-msg", "w-msg", "e-msg")


def test_error_threshold_drops_everything_below_error() -> None:
    calls: list[tuple] = []
    seen = _drain(threshold=LDD_LEVEL_RANK["error"], calls=calls)
    assert seen == ("e-msg",)


def test_warning_threshold_passes_warning_and_error() -> None:
    calls: list[tuple] = []
    seen = _drain(threshold=LDD_LEVEL_RANK["warning"], calls=calls)
    assert seen == ("w-msg", "e-msg")


# ----- event() / report() participate ----------------------------------- #


def test_event_default_level_info_passes_under_info_threshold() -> None:
    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(ctx=StderrToolContext(), sinks=(sink,), level_threshold=LDD_LEVEL_RANK["info"]):
            await ldd_event("RowFetched", rows=10)

    anyio.run(run)
    assert seen == ["RowFetched"]


def test_event_explicit_debug_level_dropped_under_info_threshold() -> None:
    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(ctx=StderrToolContext(), sinks=(sink,), level_threshold=LDD_LEVEL_RANK["info"]):
            await ldd_event("RouterEntered", level="debug")

    anyio.run(run)
    assert seen == []


def test_event_explicit_debug_level_passes_under_debug_threshold() -> None:
    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(ctx=StderrToolContext(), sinks=(sink,), level_threshold=LDD_LEVEL_RANK["debug"]):
            await ldd_event("RouterEntered", level="debug")

    anyio.run(run)
    assert seen == ["RouterEntered"]


class _R(a2kit.Router):
    slug = "r"


def test_report_default_level_info_passes() -> None:
    """report() default level=info passes under info threshold."""
    from pydantic import BaseModel

    class _Payload(BaseModel):
        n: int

    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(
            ctx=StderrToolContext(),
            sinks=(sink,),
            level_threshold=LDD_LEVEL_RANK["info"],
            report_type=_Payload,
        ):
            await ldd_report(_Payload(n=1))

    anyio.run(run)
    assert seen == ["_Payload"]


def test_report_explicit_debug_level_dropped_under_info_threshold() -> None:
    from pydantic import BaseModel

    class _Payload(BaseModel):
        n: int

    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(
            ctx=StderrToolContext(),
            sinks=(sink,),
            level_threshold=LDD_LEVEL_RANK["info"],
            report_type=_Payload,
        ):
            await ldd_report(_Payload(n=1), level="debug")

    anyio.run(run)
    assert seen == []


# ----- events_enabled kill-switch is orthogonal ------------------------- #


def test_events_enabled_off_suppresses_everything_regardless_of_threshold() -> None:
    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    async def run() -> None:
        with ldd_state_for_call(
            ctx=StderrToolContext(),
            sinks=(sink,),
            events_enabled=False,
            level_threshold=LDD_LEVEL_RANK["trace"],
        ):
            await ldd_error("critical")

    anyio.run(run)
    assert seen == []


# ----- End-to-end: App config drives dispatch-site stamp ---------------- #


class _LevelRouter(a2kit.Router):
    slug = "lvl"

    @a2kit.read()
    async def fire(self) -> dict[str, str]:
        await ldd_debug("d-msg")
        await ldd_info("i-msg")
        return {"ok": "yes"}

    tools = (fire,)


def test_dispatch_stamps_threshold_from_app_config_default(no_dotenv: Path) -> None:
    """End-to-end: default A2kitConfig.ldd.level=info silences debug() in dispatched tools."""
    from a2kit.testing import client

    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    app = a2kit.App("dispatch-default").add_router(_LevelRouter())
    app.ldd.add_sink(sink)

    async def go() -> None:
        async with client(app) as c:
            await c.invoke("fire")

    asyncio.run(go())
    assert "i-msg" in seen
    assert "d-msg" not in seen


def test_dispatch_stamps_threshold_from_app_config_debug(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    """End-to-end: A2KIT_LDD__LEVEL=debug lets debug() through."""
    monkeypatch.setenv("A2KIT_LDD__LEVEL", "debug")
    from a2kit.testing import client

    seen: list[str] = []

    async def sink(e: LddEmission) -> None:
        seen.append(e.name)

    app = a2kit.App("dispatch-debug").add_router(_LevelRouter())
    app.ldd.add_sink(sink)

    async def go() -> None:
        async with client(app) as c:
            await c.invoke("fire")

    asyncio.run(go())
    assert "d-msg" in seen
    assert "i-msg" in seen
