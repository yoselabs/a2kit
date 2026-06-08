"""Typed event emission demo — v0.27 idiom.

Two ways to emit a structured event with a registered type:

1. **Free-function form with an instance** (v0.26.1): pass the model
   directly to ``a2kit.ldd.event``. The event name defaults to
   ``type(instance).__name__``; payload serializes via ``model_dump``
   (pydantic) or ``dataclasses.asdict``. No registry needed when you
   don't also want progress reports.

2. **Registry + ``emit_typed``**: for events that also report progress
   to the MCP client. Register the model with a progress callback at
   module load; ``emit_typed`` runs ``model_dump → event →
   report_progress`` in one call.

Run as a CLI::

    python -m examples.typed_events.server jobs run --steps 3

Run as MCP::

    python -m examples.typed_events.server serve
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

import a2kit
import a2kit.log
from a2kit.config import A2kitConfig, LogConfig


class StepStarted(BaseModel):
    """Phase boundary — emitted via the free-function form below."""

    step: int
    total: int
    label: str


class StepProgressed(BaseModel):
    """Mid-step heartbeat — registered with progress callback so the MCP
    client gets a progress notification."""

    step: int
    total: int


class StepCompleted(BaseModel):
    """Phase boundary close — also reports progress."""

    step: int
    total: int
    elapsed_ms: int


class JobsRouter(a2kit.Router):
    slug = "jobs"

    @a2kit.read()
    async def run(self, *, ctx: a2kit.ToolContext, steps: int = 3) -> dict[str, int]:
        """Run ``steps`` fake work units, emitting typed records along the way.

        A typed instance rides the level method directly — ``info(instance)``
        dumps it to a structured payload (the ``event()`` verb is retired).
        For MCP progress bars, call ``ctx.report_progress(...)`` alongside.
        """
        for i in range(1, steps + 1):
            await a2kit.log.info(StepStarted(step=i, total=steps, label=f"step-{i}"))
            await a2kit.log.info(StepProgressed(step=i, total=steps))
            await ctx.report_progress(i, steps)
            await asyncio.sleep(0)
            await a2kit.log.info(StepCompleted(step=i, total=steps, elapsed_ms=1))
        return {"steps": steps}


class TypedEventsApp(a2kit.App):
    name = "typed-events-demo"
    routers = (JobsRouter,)
    config = A2kitConfig(log=LogConfig(stderr_sink="pretty"))


app = TypedEventsApp()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
