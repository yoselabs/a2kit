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


app = a2kit.App("typed-events-demo")
# Register only the events that also need progress callbacks. StepStarted
# doesn't need progress — it emits via the free function path below.
app.ldd.events.register(StepProgressed, progress=lambda e: (e.step, e.total))
app.ldd.events.register(StepCompleted, progress=lambda e: (e.step, e.total))


class JobsRouter(a2kit.Router):
    @a2kit.read()
    async def run(self, *, ctx: a2kit.ToolContext, steps: int = 3) -> dict[str, int]:
        """Run ``steps`` fake work units, emitting typed events along the way."""
        for i in range(1, steps + 1):
            # Free-function typed emit (no registry needed).
            await a2kit.ldd.event(ctx, StepStarted(step=i, total=steps, label=f"step-{i}"))
            # Registered events that also report progress use the registry.
            await app.ldd.events.emit_typed(ctx, StepProgressed(step=i, total=steps))
            await asyncio.sleep(0)
            await app.ldd.events.emit_typed(ctx, StepCompleted(step=i, total=steps, elapsed_ms=1))
        return {"steps": steps}


app.add_router(JobsRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
