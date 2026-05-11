# Field-logging via LDD primitive

## Why

`ctx.info("starting", batch=2)` — the kwargs-emit pattern taught in
`examples/streaming_logger/` and `examples/tracker/` — **crashes on
the MCP transport.** Real `fastmcp.Context.info` accepts only
`(message, logger_name=None, extra=None)`; the CLI-side
`StderrToolContext.info` accepts `(msg, **fields)`. Tools written
against the CLI shape (or against the in-process test client, which
subclasses the CLI stub) work locally but raise
`TypeError: Context.info() got an unexpected keyword argument 'batch'`
the first time a real MCP agent calls them.

A side-by-side scan of every public method on the two Contexts shows
**14 drifting signatures, 4 of which are crash-class
under MCP** (`info`, `warning`, `error`, `debug`). Two additional
methods drift in return shape (`read_resource`, `get_prompt`) and
several drift in argument acceptance (`elicit`, `log`, `sample`).
The kwarg-emit bug is the most-used face of a wider divergence.

Five layers of our defence pyramid miss it:

1. `ruff` — syntactic only.
2. `a2kit lint static` — semantic rules, no signature check.
3. `ty check src/` — internal call sites use `ctx.log(extra=...)`
   correctly; the library itself never trips the bug.
4. `ty check tests/ examples/` — not in `make lint`; would catch it if it were.
5. `tests/test_context_surface.py` — name-coverage only
   (`dir(stub) ⊇ dir(fastmcp.Context) \ MCP_ONLY`); never checks
   signatures.

Plus the load-bearing failure: `tests/test_in_process_client.py` uses
`_CapturingContext(StderrToolContext)` — a CLI subclass posing as an
"MCP test client". Every test that exercises "MCP behaviour with
logging" structurally exercises the CLI shape. The drift is
**invisible to every test path a2kit ships with.**

Production-side opacity compounds the bug. With `App(debug=False)` —
the default — the MCP wire emits `ToolError: Error calling tool 'X'`
with no further detail; a developer integrating against Claude
Desktop or any real MCP client sees no breadcrumb pointing at the
ctx-shape issue. Only `App(debug=True)` (a development-only switch)
embeds the traceback in `str(exc)`.

The architectural fault is captured **as a written-down requirement**
in `openspec/specs/mcp-context-passthrough/spec.md`. Two clauses
contradict each other:

- "The library SHALL NOT define an independent `ToolContext` Protocol
  or subclass `fastmcp.Context`."
- Stub behaviour: "`debug`, `info`, `warning`, `error` — emit a
  stderr line in the existing LDD wire format `[ +s.mmm LEVEL] msg
  key=val`." with a worked example `ctx.info("hi", x=1)`.

The first clause forbids the type surface that would make the second
clause callable on both transports. The kwarg-emit pattern works
**only** on the CLI side; the spec asserts the CLI scenario and never
asserts an MCP scenario for the same call, encoding the divergence
into the contract.

This change repairs the contract. It adopts the path the LDD
event/report primitives already took: pull the field-bearing shape
out of `ctx.*` and onto free functions. `a2kit.ldd.event(ctx, ...)`
and `a2kit.ldd.report(ctx, ...)` already branch internally on
`_is_fastmcp_context(ctx)` and emit the right wire form per transport.
**`a2kit.ldd.log` is the missing third sibling.**

## What Changes

### New free function: `a2kit.ldd.log`

`a2kit.ldd.log(ctx, level, msg, **fields)` is the protocol-neutral
field-logging primitive. Same dispatch shape as `event` / `report`:

- **MCP path** — `await ctx.log(level=..., message=..., extra=fields)`,
  honouring the existing 60-char `msg` cap and `elapsed_ms` basis from
  the LDD context-var.
- **CLI path** — calls `StderrToolContext._emit(LEVEL_LABEL, msg, fields)`
  to render the same `[ +s.mmm LEVEL] msg key=val` line tools see today.

Convenience aliases follow the existing surface: `a2kit.ldd.info`,
`warning`, `error`, `debug`. All accept `(ctx, msg, **fields)` and
delegate to `log`.

### Narrow `StderrToolContext.info/warning/error/debug` to fastmcp shape

The CLI stub's logging methods are rewritten to match
`fastmcp.Context.info(message, logger_name=None, extra=None)`
verbatim. The `**fields` kwarg signature is **removed**. The body
becomes a thin adapter that forwards to `_emit("INFO", message,
extra or {})` so the CLI rendering of `ctx.info("msg", extra={"k":1})`
matches today's `[ +s.mmm INFO    ] msg k=1` line.

`StderrToolContext._emit` is unchanged — it remains the shared backend
that both the stub's narrow methods and the new `a2kit.ldd.log` CLI
path call into.

### Migrate kwarg-emit call sites

Three locations use the broken pattern:

- `examples/streaming_logger/routers.py` — 8 calls
- `examples/tracker/routers.py` — 1 call
- `tests/test_in_process_client.py` — 2 calls
- `examples/streaming_logger/README.md` + `examples/tracker/README.md`
  — documentation snippets

Each `await ctx.info("msg", k=v)` becomes `await a2kit.ldd.info(ctx, "msg", k=v)`
(or `log(ctx, "info", ...)` for symmetry). Round-trips identically on
CLI; works on MCP for the first time.

### Replace name-coverage test with signature-compatibility test

`tests/test_context_surface.py` is rewritten. The new test enumerates
every method-call shape that appears in `tests/` and `examples/` and
asserts each is callable against **both** `fastmcp.Context` and
`StderrToolContext` with realistic args, using `inspect.signature(...).bind`.
The previous name-only check is retained as a sub-assertion (the
`MCP_ONLY` allowlist still applies for methods that exist on
fastmcp but raise on the stub).

### Rebuild the in-process test client on the real Context shape

`_CapturingContext(StderrToolContext)` is replaced with a capturing
adapter that wraps a real `fastmcp.Context`-shaped surface (or
re-anchors the test client against the same Protocol-of-record that
`signature.py`'s `is_tool_context_annotation` resolves to). The goal
is structural: the in-process test client SHALL NOT silently accept
shapes the real MCP transport rejects.

### Add `ty check tests/ examples/` to `make lint`

Once the migration completes and call sites narrow to fastmcp-shape,
`ty check tests/` and `ty check examples/` become viable as `make lint`
gates. They are added behind the existing `ty check src/` invocation.
This is what catches future drift early — if anyone re-introduces a
kwarg on `ctx.info`, ty fails at PR time.

### Documentation

- `examples/streaming_logger/README.md` and `examples/tracker/README.md`
  switch their LDD examples from `ctx.info("msg", k=v)` to
  `a2kit.ldd.info(ctx, "msg", k=v)`. The "general logging" surface
  (`ctx.info("msg")`, no fields) is documented separately as a
  passthrough to fastmcp.
- ANTIPATTERNS.md gains an entry: "Kwargs on `ctx.info/warning/error/debug`."
- The LDD section in main `README.md` documents the three sibling
  primitives (`event`, `report`, `log`) as the unified protocol-neutral
  surface.

## Capabilities

### Modified Capabilities

- `mcp-context-passthrough`: the requirement "CLI stub supplies a
  fastmcp.Context-shaped stub" tightens — the four logging methods
  SHALL match fastmcp's signature exactly, not the widened
  `**fields` form. The `LDD event and report primitives are
  protocol-neutral functions` requirement extends to cover `log`
  as a third sibling. The kwarg-emit scenario in the spec is removed
  (the example is rewritten to use `a2kit.ldd.info`).

- `type-correctness-gate`: gains `tests/` and `examples/` as ty
  check targets. The signature-compatibility test (replacement for
  `test_context_surface.py`) becomes part of the gate.

## Impact

- **Affected code**:
  - `src/a2kit/packages/ldd/__init__.py` — new `log`/`info`/`warning`/`error`/`debug` exports.
  - `src/a2kit/packages/cli/context.py` — narrow four logging methods.
  - `src/a2kit/packages/testing/client.py` — rebuild `_CapturingContext`.
  - `examples/streaming_logger/`, `examples/tracker/` — migrate call sites + README.
  - `tests/test_in_process_client.py` — migrate call sites.
  - `tests/test_context_surface.py` — rewrite as signature test.
  - `Makefile` — add `ty check tests/ examples/` to `lint`.
  - `openspec/specs/mcp-context-passthrough/spec.md` — see Modified Capabilities.

- **APIs**: BREAKING for consumers using `ctx.info("msg", k=v)`. The
  kwargs form raises `TypeError` after this change (matching what
  the MCP path does today). Migration is mechanical:
  `s/await ctx\.(info|warning|error|debug)\("([^"]*)", (.*)\)/await a2kit.ldd.\1(ctx, "\2", \3)/`.
  No consumers outside this repo are known; if any exist they were
  already broken on MCP.

- **Dependencies**: none.

- **CI cost**: `ty check tests/ examples/` adds ~2s to `make lint`.

- **Risk**:
  - The rewrite of `_CapturingContext` may surface latent bugs in
    other in-process-client tests that depend on the CLI-stub-shaped
    `_emit` capture. Mitigation: keep `_emit`-shaped capture as an
    internal sink the new client subscribes to, not as the public
    surface.
  - Once `ty check tests/` is gated, any new test that uses an
    unblessed ctx shape will fail at CI. Acceptable cost — this is
    the gate's purpose.

- **Quality bar shift**: signature-compatibility becomes a first-class
  contract test. Future drift in `elicit`, `read_resource`,
  `get_prompt` etc. — currently silent — will surface immediately.
  Those Tier 3/4 divergences are out of scope for this change but
  the test scaffold is ready to receive them.
