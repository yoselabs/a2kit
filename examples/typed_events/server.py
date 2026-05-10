"""``app.ldd.events`` typed-event registry demo.

Routers register Pydantic event models on the App's `EventRegistry` once at
module load, optionally with a progress-extraction callback. Tools then
emit instances via ``await app.ldd.events.emit_typed(ctx, evt)`` — the
registry handles ``model_dump(mode="json")``, calls
:func:`a2kit.ldd.event`, and forwards to ``ctx.report_progress`` when a
callback is registered.

Run as a CLI::

    python -m examples.typed_events.server jobs run --steps 3

Run as MCP::

    python -m examples.typed_events.server serve
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

import a2kit


class StepStarted(BaseModel):
    step: int
    total: int
    label: str


class StepCompleted(BaseModel):
    step: int
    total: int
    elapsed_ms: int


app = a2kit.App("typed-events-demo")
app.ldd.events.register(StepStarted, progress=lambda e: (e.step, e.total))
app.ldd.events.register(StepCompleted, progress=lambda e: (e.step, e.total))


class JobsRouter(a2kit.Router):
    @a2kit.read()
    async def run(self, *, ctx: a2kit.ToolContext, steps: int = 3) -> dict[str, int]:
        """Run ``steps`` fake work units, emitting typed events with progress."""
        for i in range(1, steps + 1):
            await app.ldd.events.emit_typed(ctx, StepStarted(step=i, total=steps, label=f"step-{i}"))
            await asyncio.sleep(0)
            await app.ldd.events.emit_typed(ctx, StepCompleted(step=i, total=steps, elapsed_ms=1))
        return {"steps": steps}


app.add_router(JobsRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
