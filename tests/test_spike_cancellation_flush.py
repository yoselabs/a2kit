"""Spike — does cancellation flush in-flight LDD events to the wire?

Pass criterion: events emitted at ``t < timeout`` land on stderr. An event
mid-await at ``t == timeout`` may or may not land — that's an implementation
detail. No exception bubbles that would mask the TimeoutError.

Outcome of this spike feeds Phase 1.6 of `ldd-emission-sinks/tasks.md`:
- All events flushed → no shielded scope needed in `event()`/`report()`.
- Some events dropped → add `anyio.CancelScope(shield=True)` around the emit.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr

import anyio
import pytest

from a2kit.packages.cli.context import StderrToolContext
from a2kit.packages.ldd import event as ldd_event


@pytest.mark.parametrize("budget_s", [0.3])
def test_cli_stderr_flushes_emissions_before_timeout_fires(budget_s: float) -> None:
    captured = io.StringIO()
    ctx = StderrToolContext()

    async def _body() -> None:
        for i in range(20):
            await ldd_event(ctx, "tick", seq=i)
            await anyio.sleep(0.05)

    async def _run() -> None:
        with anyio.fail_after(budget_s):
            await _body()

    with redirect_stderr(captured), pytest.raises(TimeoutError):
        anyio.run(_run)

    lines = [line for line in captured.getvalue().splitlines() if "tick" in line]
    # At ~0.05s per emit and a 0.3s budget, expect ~6 emissions.
    assert len(lines) >= 3, f"expected ≥3 tick emissions in {budget_s}s, got {len(lines)}: {lines!r}"
