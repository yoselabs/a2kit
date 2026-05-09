# streaming_logger — Logging-Driven Development with `ctx: a2kit.ToolContext`

This example demonstrates **LDD** (Logging-Driven Development): a tool
should *stream its narrative as it executes*, not just return a final
value. Long-running operations narrate themselves through
`ctx.info(...)` / `ctx.warning(...)` / `await ctx.report_progress(...)`,
and a2kit routes those updates to whichever protocol the user is on.

| Caller             | Where the stream lands                    |
|--------------------|-------------------------------------------|
| MCP client (agent) | Protocol notifications (`notifications/message`) |
| CLI user           | Stderr, one `[ +s.mmm LEVEL] msg key=val` line per call |

The tool author writes the same code in both cases.

## Why LDD

A tool that runs for 30 seconds and only ever prints its return value
*looks broken*. The agent has no idea whether you're stuck on row 1 of
1,000,000 or finished and serializing. Streamed progress is the cheapest
way to make autonomous agents (and humans) trust a slow tool.

Rules of thumb — pick the right channel for the right purpose:

| Channel | Use when... | Example |
|---|---|---|
| `ctx.info(msg, **kw)` | free-form telemetry, ambient process noise | `ctx.info("processing batch", start=i)` |
| `ctx.warning(msg, **kw)` | retryable issues, recoverable anomalies | `ctx.warning("transient failure", attempt=2)` |
| `ctx.error(msg, **kw)` | genuine errors **before** raising | `ctx.error("giving up", attempts=N)` |
| `await ctx.report_progress(i, n)` | numeric progress an agent can show as a bar | `await ctx.report_progress(i, len(rows))` |
| `await ctx.event(name, **kw)` | typed narrative milestones the agent can pattern-match | `await ctx.event("api.fetched", count=30)` |
| `await ctx.report(payload)` | typed mid-flight result chunks (declared via `@reports(...)`) | `await ctx.report(BatchReport(batch=4, accepted=12))` |

**Events vs reports.** Events are free narrative — any tool can emit, no
declaration required, payload is documentary. Reports are typed result
chunks — declared by stacking `@reports(BatchReport)` from
`a2kit.packages.mcp.reports` on top of the verb decorator, validated at
call time, schema dumped under `meta.a2kit.reportSchema`. Use events to
say "what's happening"; use reports to say "here's a piece of the answer."

**Wire format.** Every emission carries elapsed time. CLI:
`[ +s.mmm LEVEL] ...` (relative seconds with millisecond precision since
the call started). MCP: `data.elapsed_ms` integer in
`notifications/message`. Keep messages short (≤ 60 char guideline) —
long log lines burn agent context tokens.

**Kill-switch.** `--no-reports` / `--no-events` on any CLI invocation
silences that channel for the call. Programmatic:
`app.set_ldd(reports=False, events=False)`. Process-wide: env
`A2KIT_LDD=off`. Disabled emissions still type-check (so test bugs are
caught). Most-specific layer wins: flag > app > env.

## The cross-protocol contract

```python
@TasksRouter.read()
async def import_csv(
    *,
    ctx: a2kit.ToolContext,
    file: str,
    batch_size: int = 100,
) -> dict:
    ctx.info("starting import", file=file, batch_size=batch_size)
    rows = _load(file)
    ctx.info("loaded rows", count=len(rows))
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        await ctx.report_progress(i, len(rows))
        ctx.info("processing batch", start=i, size=len(batch))
        await _persist(batch)
    ctx.info("done", imported=len(rows))
    return {"imported": len(rows), "batches": (len(rows) + batch_size - 1) // batch_size}
```

`ctx` is typed as `a2kit.ToolContext` — a Protocol with `info` /
`warning` / `error` / `debug` / `report_progress`. a2kit picks the
right adapter at call time:

- CLI: `a2kit.packages.cli.context.StderrToolContext` — prints
  `[INFO] msg key=val` to stderr.
- MCP: `a2kit.packages.mcp.context.FastMCPContextAdapter` — wraps
  `fastmcp.Context` so each call becomes a protocol notification.

The agent client sees the same narrative the CLI user sees, just
encoded for the wire (see [`fastmcp.Context.info` docs](https://gofastmcp.com/python-sdk/fastmcp-context#info)).

## CLI invocation — see logs interleaved with the final result

```bash
# Make a small CSV
printf 'id,name\n1,a\n2,b\n3,c\n4,d\n5,e\n' > /tmp/x.csv

# Invoke the tool — stderr is the stream, stdout is the formatted return
uv run python -m examples.streaming_logger.server tasks import_csv \
    --file /tmp/x.csv --batch-size 2
```

You'll see something like:

```
[ +0.001 INFO    ] starting import file='/tmp/x.csv' batch_size=2
[ +0.002 INFO    ] loaded rows count=5
[ +0.003 progress] current=0 total=5
[ +0.004 INFO    ] processing batch start=0 size=2
[ +0.005 progress] current=2 total=5
[ +0.005 INFO    ] processing batch start=2 size=2
[ +0.006 progress] current=4 total=5
[ +0.006 INFO    ] processing batch start=4 size=1
[ +0.007 INFO    ] done imported=5
```

…on **stderr**, while **stdout** receives the final formatted dict
(`imported=5 batches=3` in TOON, or JSON if you pass `--format=json`).

## Buffering & "snappy" feedback

Stderr is line-buffered by default in Python. Each `ctx.info(...)`
flushes immediately — no `flush=True` needed. That means even a
multi-minute import feels live to the user as long as you call `ctx.info`
between milestones.

## MCP invocation

```bash
uv run python -m examples.streaming_logger.server serve
```

The same `ctx.info(...)` lines now travel as MCP `notifications/message`
frames. Agents wired to FastMCP receive them via their server-events
channel and can render them however they like (progress bars, log
panels, audit trails).

## Four tools, four patterns

| Tool                       | Demonstrates                                                       |
|----------------------------|--------------------------------------------------------------------|
| `import_csv`               | Batched `report_progress` + per-batch `ctx.info`.                  |
| `long_running`             | `ctx.warning` on retry, `ctx.error` before `raise`.                |
| `quick_status`             | Tool with no `ctx` param — LDD is opt-in.                          |
| `import_csv_with_reports`  | All four channels: `ctx.event` + `ctx.report` + `info` + progress. |

## Try it

```bash
uv run python -m examples.streaming_logger.server --help
uv run python -m examples.streaming_logger.server tasks import_csv \
    --file /tmp/x.csv --batch-size 2
uv run python -m examples.streaming_logger.server tasks long_running --attempts 2
uv run python -m examples.streaming_logger.server tasks quick_status
uv run python -m examples.streaming_logger.server serve
```
