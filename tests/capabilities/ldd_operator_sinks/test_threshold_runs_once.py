"""Capability: a sub-threshold emission reaches NEITHER operator nor wire.

The level threshold is the single volume control; when it drops an
emission, the producer returns before any sink or wire call.
"""

from __future__ import annotations

import anyio

from a2kit.ldd import event as ldd_event
from a2kit.packages.ldd.ambient import ldd_state_for_call
from a2kit.packages.ldd.levels import LDD_LEVEL_RANK
from a2kit.packages.ldd.sinks import LddEmission
from a2kit.packages.testing.null_context import null_context


def test_sub_threshold_emission_skips_operator_and_wire() -> None:
    observed: list[LddEmission] = []

    async def _sink(em: LddEmission) -> None:
        observed.append(em)

    async def _run() -> None:
        # Threshold set to "warn" (rank 3); event() defaults to "info"
        # (rank 2), below threshold → dropped.
        with ldd_state_for_call(
            ctx=null_context(),
            sinks=(_sink,),
            level_threshold=LDD_LEVEL_RANK["warning"],
        ):
            await ldd_event("Sub", level="info")

    anyio.run(_run)
    assert observed == []
