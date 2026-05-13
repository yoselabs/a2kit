# Rebuild the in-process test client on the real fastmcp.Context

## Why

The current in-process test client (`a2kit.testing.client` →
`_CapturingContext(StderrToolContext)`) subclasses the CLI stub. It
**structurally cannot see** any divergence between
`StderrToolContext` and `fastmcp.Context`. The kwarg-on-info crash
that motivated the `field-logging-via-ldd` change was invisible to
every test path a2kit shipped with for exactly this reason: tests
written against the in-process client exercised the CLI shape, not
the MCP shape, and nobody noticed.

After `field-logging-via-ldd` landed:

- The new `tests/test_field_logging_mcp_path.py` repro suite is the
  *only* place in the codebase that exercises a tool through a real
  `fastmcp.Client(transport=build_mcp_server(app))`.
- `_CapturingContext` is still a CLI subclass. New ctx-shape bugs in
  any of the 13 still-drifting methods (`elicit`, `read_resource`,
  `get_prompt`, etc.) would slip past the in-process client the same
  way the kwarg bug did.

The signature-compatibility test (`tests/test_context_surface.py`)
helps but is bind-only — it asserts call shapes *can* bind against
both Context impls; it does not assert that the calls **behave the
same**. Two impls can have matching signatures and diverging return
types, side-effects, or error modes. Only a real-transport test
client catches behavioural drift.

This change replaces `_CapturingContext` with a thin adapter built
on top of a real in-memory `fastmcp.Client` connected to
`build_mcp_server(app)`. The public API of `a2kit.testing.client`
(`async with client(app) as c: await c.invoke(...)`,
`c.events`, `c.progress`, `c.logs`) stays unchanged — consumers see
no migration. Internally, the test client now runs the real
FastMCP server in-memory, captures `notifications/message` through a
client-side log handler, and surfaces them as the same `events` /
`logs` / `progress` lists the existing API exposes.

## What Changes

### Internal architecture flip

`_CapturingContext(StderrToolContext)` is **deleted**. The
`TestClient` instead:

- Builds a `FastMCP` server via `build_mcp_server(app)`.
- Opens a `fastmcp.Client(transport=server, log_handler=...,
  progress_handler=...)`.
- Routes inbound `notifications/message` to the capturing lists by
  inspecting `extra["a2kit_kind"]` (`"event"` / `"report"` / `"log"`)
  to fan out into `events` / `reports` / `logs`.
- Surfaces `progress_handler` notifications into a `progress` list of
  `(current, total)` tuples — same shape the existing API uses.

The result: every dispatch goes through the real FastMCP dispatcher,
the real fastmcp.Context, and the real wire-format encoding. CLI-only
behaviour and MCP-only behaviour can no longer disagree silently.

### Public API: unchanged

The exported `client(app)` callable, the `TestClient` class, and its
`invoke`, `events`, `reports`, `logs`, `progress`, `render_as` members
keep the same names and call shapes. Existing tests that use the
client (`tests/test_in_process_client.py`,
`tests/examples/streaming_logger/test_server.py`, etc.) compile
unchanged; the change is structural, not API-level.

One nuance: `logs` today is `list[str]` of pre-rendered LDD lines.
The new client receives structured `notifications/message` payloads,
so it produces `list[LogLine]` (level + message + fields +
elapsed_ms) by default and exposes a `c.logs_text` property that
formats them with `format_ldd_line` for tests that asserted on the
rendered form. Migration: any test that did `"INFO" in c.logs[0]`
swaps to `"INFO" == c.logs[0].level` or `"INFO" in c.logs_text[0]`.

### Concurrency and lifecycle

The FastMCP in-memory transport runs the server in the same event
loop as the test. `async with client(app) as c` opens the transport
in `__aenter__` and closes it in `__aexit__`, same as today. The
lifecycle hooks (`@app.on_startup` / `@app.on_shutdown`) wired to the
real server now run during the context-manager scope — this is a
**behavioural improvement**: today's `_CapturingContext` bypassed the
server lifecycle entirely, so tests that depended on
`@on_startup`-resolved state had to hack around it.

### Direct ctx-shape exposure

After the rewrite, tools dispatched through the test client receive
the actual `fastmcp.Context`. Any test or example that did
`ctx.info("msg", k=v)` against the in-process client (and got away
with it because of the CLI subclass) now fails the same way it would
on production MCP. Since `field-logging-via-ldd` already migrated
those call sites, this is enforcement, not migration.

### Documentation

- The README "Testing tools" section documents that the in-process
  client now runs the real FastMCP server in-memory; the test client
  is a thin capture layer over `fastmcp.Client`.
- Tests in `tests/test_in_process_client.py` get a docstring note
  that the client is real-transport-backed; any new test added to
  this file is structurally a transport-level test, not a unit test.

## Capabilities

### Modified Capabilities

- `in-process-test-client`: the implementation requirement flips
  from "CLI-stub-backed capture" to "real-fastmcp-transport-backed
  capture." Public API unchanged. New scenario: tool invocation
  through the client exercises the same fastmcp.Context the
  production MCP transport uses.

## Impact

- **Affected code**:
  - `src/a2kit/packages/testing/client.py` — full rewrite.
  - `src/a2kit/packages/testing/__init__.py` — possibly re-exports.
  - `tests/test_in_process_client.py` — assertion shape adjusted
    (`logs` now structured).
  - `tests/test_ldd_sinks.py`, `tests/test_typed_emit.py`,
    `tests/test_event_registry.py` — sweep for `c.logs` consumers.
  - Any example `tests/examples/*/test_server.py` that constructs a
    `TestClient` directly (most use the higher-level CLI helpers and
    are unaffected).

- **APIs**: BREAKING for the test-client internals (`_CapturingContext`
  was never public, but any test that imported it directly breaks).
  No external user is known to depend on it; this is a structural
  internal.

- **Dependencies**: none. `fastmcp.Client` and `FastMCP` in-memory
  transport are already required.

- **CI cost**: the in-process client is slightly slower per invoke
  (~+2-5ms for server setup) but suite-level cost is negligible
  (~50ms across the ~10 client-using tests).

- **Quality bar shift**: tests that ran "MCP-shaped" code via the CLI
  subclass now genuinely run it via FastMCP. Any drift in the
  remaining 13 Context methods (which `align-context-method-signatures`
  is independently addressing) surfaces here too.

- **Risk**: in-memory transport behaviour edge cases. FastMCP's
  in-memory transport is well-trodden in fastmcp's own test suite;
  primary unknown is interaction with our `App.on_startup`/
  `on_shutdown` wiring. Mitigation: phase 0 prerequisite is a
  ground-up smoke that confirms every existing
  `tests/test_in_process_client.py` scenario passes against the new
  client, then iterate.
