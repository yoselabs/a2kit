# Per-tool timeout decorator kwarg (`timeout=...`)

## Why

`OPERATIONAL_CONTRACTS` Q2 documents the current contract: no
built-in timeout; tools wrap their own body in
`anyio.fail_after(seconds)`. The pattern is repetitive across every
network-facing tool (a2web's `fetch`, `mcp__a2db__execute`, etc.).
Wrapping each body individually:

- repeats `async with anyio.fail_after(...):` mechanically
- forces the timeout into the tool body (where it's invisible to
  callers reading the decorator) instead of the contract surface
- doesn't surface in `inputSchema` / `ToolAnnotations`, so agent
  callers don't see what budget the tool advertises

Per the devil's-advocate analysis of deferred wish #2: this is
**not** sugar over `anyio.fail_after`. Framework-owned timeout
slots the cancel scope **outside the LDD scope** (so LDD `event()`
calls during teardown don't race the deadline) and **inside the
dispatcher's lifecycle unwind** (so resource cleanup runs).
Per-tool coordination with `App(default_timeout=...)` and surfacing
in tool annotations are framework concerns, not call-site sugar.

## What Changes

- Verb decorators (`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`)
  accept a new `timeout` keyword argument:
  - `timeout=None` (default) — current behaviour; tool owns its
    budget.
  - `timeout=60` or `timeout=60.0` — float seconds.
  - `timeout="60s"` or `timeout="2m"` or `timeout="500ms"` —
    string with unit suffix (`ms`/`s`/`m`).

- `A2KitMetaExtras` gains a `timeout_seconds: float | None` field.
  The decorator parses the string form at decoration time and
  stores the canonical float-seconds value.

- New wrapper `_wrap_with_timeout(fn, *, seconds)` lives in
  `packages/mcp/server.py`. Installed as the **innermost** wrapper
  (closest to `fn`), so the cancel scope sits inside the LDD scope
  (LDD emissions during a timeout's unwind window still see the
  ambient state) and inside the dispatch-hook (DI is resolved
  before the budget starts ticking). Uses
  `anyio.fail_after(seconds)`.

- On timeout, the wrapper raises Python's `TimeoutError`. The
  outermost `_wrap_with_error_envelope` (from
  `mcp-structured-wire-error-envelope`) wraps it into the standard
  `{"class": "TimeoutError", "message": ...}` JSON envelope on
  the MCP wire.

- The CLI runtime gains the same wrapper at
  `cli/runtime.py:_invoke_tool_in_process`, so a tool's
  `timeout=` is honored identically on both transports.

- `A2KitMeta.annotations_as_dict()` surfaces `timeout_seconds` (when
  set) under the `a2kit` extras key so MCP consumers reading
  `tool.meta` see the budget.

- `OPERATIONAL_CONTRACTS` Q2 (per-tool timeouts) updated to
  describe the new mechanism. The existing "no built-in,
  use `anyio.fail_after`" recommendation becomes a fallback for
  tools that need non-uniform timeouts inside their body.

## Impact

- **Affected specs**: `verb-decorators` — adds the `timeout=`
  kwarg requirement and timeout-meta surfacing scenarios.
- **Affected code**:
  - `src/a2kit/tool.py` — `read`/`write`/`list_` decorators accept
    `timeout=`, parse the form, pass to `_stamp` → `A2KitMetaExtras`.
  - `src/a2kit/metadata.py` — `A2KitMetaExtras.timeout_seconds`
    field; `annotations_as_dict()` surfaces it.
  - `src/a2kit/packages/mcp/server.py` — `_wrap_with_timeout`;
    wrapper-chain assembly installs it innermost when
    `meta.extras.timeout_seconds` is set.
  - `src/a2kit/packages/cli/runtime.py` — same wrapper at the
    CLI dispatch site (inside `_invoke_tool_in_process`).
  - `OPERATIONAL_CONTRACTS.md` — Q2 update.
  - `tests/test_timeout_decorator.py` — new file. Covers
    string-form parsing, MCP transport behaviour, CLI transport
    behaviour, envelope JSON shape on timeout, and
    `TimeoutError` class round-trip.
- **APIs**: NON-BREAKING. Default `timeout=None` preserves all
  current behaviour. The new wrapper only fires when set.
- **Dependencies**: `anyio` already a transitive dep; no new
  imports.
- **CI cost**: ~5 new tests; negligible.
- **Risk**:
  - **Async-cancellation propagation**: `anyio.fail_after` raises
    `TimeoutError` (Python's, not `asyncio.TimeoutError`).
    `_wrap_with_error_envelope` catches it as `Exception` and
    wraps. `CancelledError` paths (per `operational-contracts`
    Q1) are not affected — the timeout wrapper is downstream of
    those.
  - **Test-client interaction**: `rebuild-test-client-on-real-context`
    routes through real FastMCP transport, so the same
    `_wrap_with_timeout` runs in tests. Tests asserting on a
    `TimeoutError` parse the envelope (`payload["class"] ==
    "TimeoutError"`).
- **Out of scope**:
  - `App(default_timeout=...)` precedence — separate change once
    a consumer wants App-wide defaults.
  - Per-tool retry policy. Tool annotations surface
    `timeout_seconds`; retry is a caller concern.
