"""LDD demo routers — stream progress through ``ctx: a2kit.ToolContext``.

Each tool emits ``a2kit.ldd.info`` / ``warning`` / ``error`` plus
``ctx.report_progress`` calls as it executes. Same code paths over MCP
(notifications) and CLI (stderr lines).

Field-bearing logging lives on ``a2kit.ldd.*`` (third sibling of
``event`` / ``report``); the plain ``ctx.info("msg")`` form is reserved
for fastmcp's narrow signature and SHOULD NOT take field kwargs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

import a2kit
from a2kit.log import error, info, warning


class ImportStarted(BaseModel):
    """Typed start-of-import event — emitted via the v0.26.1 instance form."""

    file: str
    batch_size: int


class ImportComplete(BaseModel):
    """Typed end-of-import event — paired with ImportStarted."""

    imported: int


class BatchReport(BaseModel):
    """Typed mid-flight chunk emitted via ``a2kit.ldd.report``.

    Distinct from ``ctx.info`` (free-form telemetry) — agents can
    pattern-match on the type and consume rows incrementally.
    """

    batch: int
    accepted: int
    rejected: int


def _load_csv(path: str) -> list[dict[str, str]]:
    """Trivial CSV-ish loader — first line is header, rest are rows.

    Kept dependency-free so the example runs without pandas / csv config.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(",")]
    out: list[dict[str, str]] = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.split(",")]
        out.append(dict(zip(header, cells, strict=False)))
    return out


async def _persist(_batch: list[dict[str, str]]) -> None:
    """Stand-in for a real async write — yields control so progress streams."""
    await asyncio.sleep(0)


class TasksRouter(a2kit.Router):
    slug = "tasks"

    @a2kit.read()
    async def import_csv(
        self,
        *,
        ctx: a2kit.ToolContext,
        file: str,
        batch_size: int = 100,
    ) -> dict[str, int]:
        """Stream a CSV import in batches.

        Demonstrates the LDD pattern: each milestone is an ``a2kit.ldd.info``
        call so the agent / CLI user sees the narrative interleaved
        with the final return value.
        """
        await info("starting import", file=file, batch_size=batch_size)
        rows = _load_csv(file)
        await info("loaded rows", count=len(rows))
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            await ctx.report_progress(i, len(rows))
            await info("processing batch", start=i, size=len(batch))
            await _persist(batch)
        await info("done", imported=len(rows))
        return {
            "imported": len(rows),
            "batches": (len(rows) + batch_size - 1) // batch_size if rows else 0,
        }

    @a2kit.read()
    async def long_running(
        self,
        *,
        ctx: a2kit.ToolContext,
        attempts: int = 3,
        fail_after: int = 5,
    ) -> dict[str, int]:
        """Showcase ``a2kit.ldd.warning`` on retryable issues, ``error`` before giving up.

        ``attempts`` retries are made; if all fail, the tool emits an
        ``error`` line then raises.
        """
        await info("long_running start", attempts=attempts)
        for attempt in range(1, attempts + 1):
            await info("attempt", n=attempt)
            await asyncio.sleep(0)
            if attempt < attempts:
                await warning("transient failure, retrying", attempt=attempt)
                continue
            if fail_after >= 0 and attempts > fail_after:
                await error("giving up", attempts=attempts)
                raise RuntimeError("long_running exceeded retry budget")
            await info("succeeded", attempt=attempt)
            return {"attempts": attempt, "ok": 1}
        # Unreachable in practice; included so type checkers see a return.
        return {"attempts": attempts, "ok": 0}

    @a2kit.read(reports=BatchReport)
    async def import_csv_with_reports(
        self,
        *,
        ctx: a2kit.ToolContext,
        file: str,
        batch_size: int = 100,
    ) -> dict[str, int]:
        """LDD with the four channels at once.

        - ``await info(name, ...)`` for narrative milestones
          (``import.started``, ``import.complete``).
        - ``await info(BatchReport(...))`` for typed mid-flight result chunks.
        - ``await info(...)`` for free-form fielded telemetry.
        - ``ctx.report_progress(i, total)`` for numeric progress.
        """
        # Typed instance form — name = type name, payload from model_dump.
        await info(ImportStarted(file=file, batch_size=batch_size))
        rows = _load_csv(file)
        await info("loaded rows", count=len(rows))
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            await ctx.report_progress(i, len(rows))
            await _persist(batch)
            await info(BatchReport(batch=i // batch_size, accepted=len(batch), rejected=0))
        await info(ImportComplete(imported=len(rows)))
        return {
            "imported": len(rows),
            "batches": (len(rows) + batch_size - 1) // batch_size if rows else 0,
        }

    @a2kit.read()
    async def quick_status(self) -> dict[str, str]:
        """Contrast: a tool with no ``ctx`` parameter — opting out of LDD entirely.

        Tools opt INTO context. There's no penalty for staying silent on
        fast operations.
        """
        return {"status": "ok"}

    tools = (
        import_csv,
        long_running,
        import_csv_with_reports,
        quick_status,
    )
