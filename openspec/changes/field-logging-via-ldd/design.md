# Design — field-logging via LDD primitive

## Context

`a2kit.ToolContext` is a lazy re-export of `fastmcp.Context`. The
CLI stub `StderrToolContext` mirrors fastmcp's public surface so tools
can run portably across CLI (`<app> tasks t`) and MCP
(`<app> serve`) transports without branching. This portability is
currently a lie for one common operation: **structured logging with
fields**. The CLI stub took the liberty of widening
`info/warning/error/debug` to accept `**fields`; the MCP path uses
the upstream narrow signature. Tools written for the wide shape crash
on the MCP wire.

The widening was a local convenience that solved an immediate
problem: tools wanted to emit narrative-with-data
(`ctx.info("starting", file="/x", batch_size=100)`) and the LDD
wire format wanted those fields as structured key=value pairs.
Adding `**fields` to the CLI stub was the quickest path to
`[ +s.mmm INFO    ] starting file=/x batch_size=100` on stderr.

That decision was correct for the **rendering**; it was incorrect for
the **method name**. The fastmcp-native `ctx.info` is a transport
primitive: "log this string to the MCP client" (or stderr on CLI).
The thing tools actually want — structured narrative with fields,
capped text, elapsed_ms, dual-transport wire format — is an
a2kit-owned concept. a2kit already has free functions
(`a2kit.ldd.event`, `a2kit.ldd.report`) for exactly this category of
operation, and those functions branch internally on the live ctx type
to pick the right wire shape. **Logging never got the same
treatment.** This change closes that gap.

## Goals / Non-Goals

### Goals

- Restore `ctx.info/warning/error/debug` to fastmcp's narrow upstream
  signature on both transports. Calls of the form `ctx.info("msg")`
  and `ctx.info("msg", extra={"k": 1})` work identically on CLI and
  MCP and render the same `[ +s.mmm INFO    ] msg k=1` line on
  stderr / MCP wire.
- Provide `a2kit.ldd.log(ctx, level, msg, **fields)` as the
  protocol-neutral field-logging primitive, alongside `event` and
  `report`. Add `a2kit.ldd.info/warning/error/debug` as convenience
  aliases.
- Replace `tests/test_context_surface.py` with a
  signature-compatibility test that pins call shapes used across
  `tests/` + `examples/` to both Context impls.
- Gate `tests/` and `examples/` under `ty check` in `make lint`.

### Non-Goals

- Fixing the **other 13 drifting methods** (`elicit`,
  `read_resource`, `get_prompt`, `log`, `sample*`, `send_notification`,
  `send_log_message`). They have their own designs to write. This
  change ships the test scaffold that surfaces them, but the
  rewrites are sequenced separately to keep blast radius bounded.
- Adopting a `ToolContext` Protocol. The existing spec
  (`mcp-context-passthrough`) forbids it; this change keeps that
  decision and routes field-logging through free functions instead.
  If the Protocol becomes desirable later, it's a separate change.
- Rewriting the LDD wire format. `format_ldd_line` is unchanged.
  The 60-char `msg` cap, `elapsed_ms` basis, and `key=value`
  rendering all carry over.
- Logging on lifecycle hooks (`@on_startup` / `@on_shutdown`). Those
  don't take ctx; if they need to log they use the existing
  `_APP_START_MONOTONIC` fallback path. Out of scope.

## Decisions

### D-LDD-LOG — `a2kit.ldd.log` is the new entry point

Add to `src/a2kit/packages/ldd/__init__.py`:

```python
async def log(
    ctx: Any,
    level: Literal["debug", "info", "warning", "error"],
    msg_or_instance: str | Any,
    /,
    **fields: Any,
) -> None:
    """Structured-narrative log with fields, transport-neutral.

    Two call forms, mirroring ``a2kit.ldd.event``:

    1. **String form**: ``log(ctx, "info", "msg", k=v, ...)``. Third
       positional is the human-readable message; remaining kwargs
       become the structured fields.
    2. **Instance form**: ``log(ctx, "info", instance)``. Third
       positional is a dataclass / pydantic ``BaseModel`` / object.
       Message defaults to ``type(instance).__name__``; fields derive
       via ``model_dump(mode="json")`` (pydantic),
       ``dataclasses.asdict`` (dataclass), or ``vars(instance)``
       (fallback). ``Enum`` values are unwrapped to ``.value``.
       Mirrors ``event``'s coercion rules verbatim — they share a
       helper.

    MCP path emits ``ctx.log(level=level, message=msg, extra=fields)``
    with the LDD elapsed_ms basis applied to a copy of fields.
    CLI path calls the stub's ``_emit`` with the level label, capped
    msg, and fields dict.
    """
```

`info/warning/error/debug` are thin wrappers that accept either form
and forward to `log`:

```python
async def info(ctx, msg_or_instance, /, **fields):
    return await log(ctx, "info", msg_or_instance, **fields)
```

Dispatch uses the existing `_is_fastmcp_context(ctx)` identity check
that `event` and `report` already share. No new branching
infrastructure. The string/instance discrimination uses the same
helper `event` already has (`_resolve_payload(name_or_instance, kwargs)`);
both call sites share it so the coercion rules can never drift.

### D-MSG-CAP — `msg` is capped before transport

Today, only the CLI rendering caps text at 60 chars (`_cap_text`
inside `format_ldd_line`). The MCP path emits the full message to the
client. To preserve "both transports agree on payload contents", the
new `log` SHALL cap `msg` before delivering to either transport — the
MCP `ctx.log(message=...)` receives the capped form. This is a
deliberate **tightening** of the wire format invariant; it matches
the existing event/report behaviour.

### D-EXTRA-BASIS — `elapsed_ms` is added to fields on MCP

The MCP-side `ctx.log(level, message, extra=fields)` call sets
`extra["elapsed_ms"] = <ms since LDD basis>` before delivery, matching
how `event` and `report` already inject elapsed_ms. The CLI side
already includes elapsed_ms via `_emit`'s line format. Both
transports carry the same key.

### D-CTX-INFO — narrow the stub to fastmcp shape

`StderrToolContext.info` (and `warning/error/debug`) become:

```python
async def info(
    self,
    message: str,
    logger_name: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    fields = dict(extra) if extra else {}
    if logger_name:
        fields["logger"] = logger_name
    self._emit("INFO", message, fields)
```

This is the same body as the existing `log` method, specialised per
level. The four-method block compresses to a single helper plus
four 2-line dispatchers.

`_emit` is unchanged. Tools using `ctx.info("msg", extra={"k": 1})`
on the CLI path render identically to today's `ctx.info("msg", k=1)`
form.

### D-NO-PROTOCOL — keep the re-export

The existing `mcp-context-passthrough` requirement
"SHALL NOT define an independent `ToolContext` Protocol" stands.
Reason: the value of a Protocol comes from the call sites it
typechecks. Once field-bearing logging moves off `ctx.*`, the
remaining `ctx.*` surface is fastmcp's. There is nothing to abstract.
Adding a Protocol now would be ceremony without payload.

If future drift surfaces in `elicit`/`read_resource`/`get_prompt` and
the chosen fix is a wrapper rather than a free-function pull-out, the
Protocol comes back on the table. Not this change.

### D-IPC-CLIENT — rebuild `_CapturingContext` on the real shape

`_CapturingContext` today subclasses `StderrToolContext`. Once the
stub narrows, the subclass narrows too — automatically. The
remaining risk is its capture semantics: it currently overrides
`_emit` to append to `self.logs`. After the narrowing, every code
path still routes through `_emit`, so capture continues to work.

The change is minimal: confirm `_CapturingContext` no longer relies
on the widened `info` signature in its own implementation (it
doesn't today; it overrides `_emit` only). The test client API
stays the same; consumers writing
`async with client(app) as c: ...` see no change.

The structural risk we accept: `_CapturingContext` is still a CLI
subclass; it does not exercise the real fastmcp.Context machinery.
Closing that gap would mean running an actual FastMCP transport in
memory, which is a much larger change and out of scope. The new
signature-compatibility test (D-SIG-TEST) provides the bridge: it
asserts that whatever shapes the in-process client accepts are also
accepted by the real fastmcp.Context.

### D-SIG-TEST — signature-compatibility test

`tests/test_context_surface.py` is rewritten. New test enumerates
**every method-call shape** used in `tests/` and `examples/`:

```python
# Build the call inventory:
CALL_SHAPES: list[tuple[str, tuple, dict]] = [
    ("info", ("msg",), {}),
    ("info", ("msg",), {"extra": {"k": 1}}),
    ("warning", ("msg",), {"extra": {"k": 1}}),
    ("report_progress", (0.5,), {"total": 1.0}),
    ("read_resource", ("file:///x",), {}),
    ("elicit", ("prompt",), {"response_type": str}),
    # ...
]

# Assert each shape binds against both Contexts:
for name, args, kwargs in CALL_SHAPES:
    inspect.signature(getattr(StderrToolContext, name)).bind(None, *args, **kwargs)
    inspect.signature(getattr(fastmcp.Context, name)).bind(None, *args, **kwargs)
```

The test fails loudly if any shape is unbindable on either side. New
patterns added to test/example code are added to `CALL_SHAPES`; the
test becomes a registry of "what does a2kit promise consumers can
call on ctx."

The previous `test_stub_covers_fastmcp_context_surface` (name-only)
is kept as a sibling assertion — covers the MCP_ONLY allowlist
contract — but is no longer the contract's load-bearing test.

### D-LINT-EXTEND — `ty check tests/ examples/` in `make lint`

After the migration, the residual ty errors in `tests/` and
`examples/` should be zero. `Makefile` `lint` target gains two
lines:

```make
lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check src/
	uv run ty check tests/
	uv run ty check examples/
	uv run a2kit lint static src/ tests/ examples/
```

Cost: ~2s on top of the existing run. Payoff: every PR that
re-introduces a kwarg on `ctx.info` (or any future shape drift)
fails statically.

### D-DOC — README and ANTIPATTERNS

`examples/streaming_logger/README.md` and
`examples/tracker/README.md` swap their narrative snippets:

```diff
-await ctx.info("starting import", file=file, batch_size=batch_size)
+await a2kit.ldd.info(ctx, "starting import", file=file, batch_size=batch_size)
```

ANTIPATTERNS.md gains an entry:

> **Don't pass fields as kwargs to `ctx.info/warning/error/debug`.**
> Use `a2kit.ldd.info(ctx, "msg", **fields)` instead. The bare
> `ctx.info("msg")` and `ctx.info("msg", extra={"k": v})` forms are
> fastmcp passthroughs; the field-bearing structured form lives on
> `a2kit.ldd.*` so it works identically on CLI and MCP.

## Alternatives Considered

### Alt-A — wrap `fastmcp.Context` on the MCP path

Build a `FastMCPContextAdapter(fastmcp.Context)` proxy that translates
`info(msg, **fields)` → `await real.info(msg, extra=fields)` and is
the actual `ctx` passed to tools.

Rejected. The existing `mcp-context-passthrough` spec explicitly
forbids this:

> The MCP runtime adapter SHALL pass the live `fastmcp.Context`
> instance directly to a tool's `ctx` parameter without wrapping or
> translation. The library SHALL NOT ship `FastMCPContextAdapter`
> or any equivalent passthrough wrapper.

Reversing that decision is a separate, larger change. The motivation
that drove the original prohibition — keep `ctx` as the real fastmcp
object so users can drop into native FastMCP features (`ctx.session`,
`ctx.request_context`, etc.) without indirection — still holds.

### Alt-B — adopt a `ToolContext` Protocol, keep methods on ctx

Define `class ToolContext(Protocol)` with `info(self, msg, **fields)`
and friends; assert both `fastmcp.Context` and `StderrToolContext`
satisfy it.

Rejected. fastmcp.Context **does not** satisfy a `**fields`-shaped
Protocol — its `info` is positional/extra-keyword only. We'd be back
to Alt-A (wrap to make the Protocol satisfied) or making the
Protocol structurally identical to fastmcp.Context (in which case
the kwarg pattern remains broken).

### Alt-C — keep `**fields` on stub, document as CLI-only

Tools using kwargs would be CLI-only by contract. Examples and
in-process tests already exercise that path; MCP tools written this
way are user error.

Rejected. The kwarg pattern is taught in README examples as the
canonical LDD-style logging. Telling users "the pattern we show you
is CLI-only and breaks on MCP" is the worst of both worlds:
keeps the bug, demands user discipline to avoid it.

### Alt-D — add `log` to `ctx`, deprecate kwargs gradually

Ship `ctx.log_field("msg", **fields)` as a new ctx method with
fastmcp-compatible wrapping; deprecate `ctx.info(msg, **fields)` over
two releases.

Rejected. Multiplies the ctx surface. Forces a deprecation window
nobody outside us is on. The free-function path is what `event` and
`report` already do; adding a third sibling is consistent with the
LDD precedent.

## Open Questions

1. **Should the rewritten `_CapturingContext` expose
   `client.logs: list[LogLine]` as a structured capture (level, msg,
   fields, elapsed_ms)?** Today it's `list[str]` of rendered lines.
   Structured capture is easier to assert against in tests. Decide
   during D-IPC-CLIENT implementation.

2. **`ty check tests/` may surface unrelated errors today** —
   third-party stubs, dynamic fixtures, etc. If the diff is too
   noisy, gate `examples/` only initially and queue `tests/` for a
   follow-up.

3. **Should we ship the rewritten `mcp-context-passthrough` scenarios
   as a separate review pass?** The proposal's Modified Capabilities
   says yes (the kwarg scenario goes away, a new MCP-path scenario
   appears). Worth a careful diff during implementation.
