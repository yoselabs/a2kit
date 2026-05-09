## Why

The v1.0 thin-core refactor (`simplify-and-thin-core`) shipped a structurally
clean codebase, but several leftover items lingered in subagent reports and
post-merge inspection: coverage at 77 % vs. the 95 % aspiration, three
deferred "bad tastes" in cross-package coupling, a few rules stubbed mid-flight,
and ergonomic rough edges in the example + CLI option synthesis. Before the
v1.0 tag goes out, sweep the debt so the reference codebase reflects the
discipline its specs claim.

This change also closes the loop on two follow-ups the user requested
during the v1.0 work but that are scoped here for review-and-merge:
ty as a hard lint gate, and a new opt-in `a2kit.packages.otel` adapter
plus an LDD (Logging-Driven Development) example.

## What Changes

### Cross-package coupling

- **Relocate `_APP_CTX`** out of `a2kit.packages.mcp.cli` (where it's a
  fastmcp-adjacent module) into a neutral home —
  `a2kit.packages.cli.app_ctx`. The convention "the cli package owns CLI
  context" replaces "mcp owns the contextvar because it landed first".
- **Relocate `compute_schema`** from `a2kit.packages.testing.snapshots` to
  `a2kit.packages.cli.schemas` and have `testing.snapshots` import from
  there. Aligns with "the cli package owns CLI-shaped schemas" while
  testing snapshot serialization stays in testing.

### Coverage uplift to 95 %

- Add focused tests for `lint/static.py` AST branches (currently 69 %).
  Target each new v1.0 rule (A2K-DI-*, A2K-CONN-LIST-PLACEHOLDER,
  A2K-IMPORT-DISCIPLINE) with positive + negative fixtures.
- Add end-to-end MCP `await server._mcp_call_tool(...)` test exercising
  `mcp/listview.py` (currently 36 %) — covers the result-rewriting path
  the unit tests skip.
- Add coverage gate: `--cov-fail-under=95` once the bar is met.

### Lint health

- Split `lint/static.py` (987 SLOC, triggers its own A2K014) into focused
  rule modules under `packages/lint/rules/` — keep the public
  `run_static` entry point; group rules by family (DI, conn, import,
  budget, select).
- Remove the stubbed A2K010 (legacy `--select` unknown-atom rule).
  v1.0 ships CEL; legacy atom validation is not a concern.

### Type-correctness gate

- **NEW capability** `type-correctness-gate`: `uv run ty check src/`
  must exit 0 on every PR. `make lint` runs ty alongside ruff +
  `a2kit lint static`. Hard CI gate.
- Add ty configuration to `pyproject.toml` (`[tool.ty.rules]` overrides
  for unfixable third-party-stub patterns, with rationale comments).

### Test layout uniformity

- Resolve `tests/packages/select/` missing `__init__.py` shadowing of the
  stdlib `select` module. Two options: rename test dir or set
  `[tool.pytest.ini_options] importmode = "importlib"` so each test
  module is loaded by file path. Pick one consistent rule.

### CLI polish

- Auto-derived option synthesis handles `Optional[T]` / `T | None` for
  primitive `T` (currently falls through to JSON-decode mode for
  nullable primitives, which is non-obvious).
- Schema-dump output respects a sensible character cap; large schemas
  produce a `... (truncated)` marker rather than overrun.

### Example ergonomics

- Replace the tracker example's module-level mutable `_impl` slot in
  `examples/tracker/deps.py` with a cleaner pattern — either
  `app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)` or
  ContextVar-based wiring. The current pattern works but reads as
  legacy.

### OTel adapter (new package)

- **NEW capability** `otel-adapter`: `a2kit.packages.otel` opt-in plugin.
  - `install(server)` adds an OTel-compatible Middleware that wraps
    every tool call in a span pulling attributes from `A2KitMeta`.
  - Optional metric counters: `a2kit.tool.calls{tool, verb, status}`.
  - OTel deps optional via `pip install 'a2kit[otel]'`. Lazy import.
  - a2kit core stays OTel-free.

### LDD example (new)

- `examples/streaming_logger/`: minimal MCP showing tools that stream
  `ctx.info` / `ctx.warning` / `await ctx.report_progress` updates
  during execution. Same code emits MCP wire notifications under
  `serve` and stderr lines under CLI invocation.
- README documents Logging-Driven Development as a discipline (when
  to emit, levels, the cross-protocol contract).

### Documentation drift

- Audit `ANTIPATTERNS.md` entries 1-13 (legacy v0.x lessons) against
  v1.0 reality. Rewrite or delete entries whose mitigation moved
  elsewhere.
- README API surface table: confirm row count + symbol coverage stays
  honest after this change lands (current: 20 rows; budget: ≤ 25).

## Capabilities

### New Capabilities

- `type-correctness-gate`: `uv run ty check src/` must pass with zero
  errors as a hard CI lint gate. ty integrates into `make lint`.
- `otel-adapter`: opt-in `a2kit.packages.otel` plugin emitting OTel
  spans + metrics for every tool call without forcing OTel into core
  deps.

### Modified Capabilities

- `thin-core-surface`: refines CLI option synthesis to handle
  `Optional[T]` / `T | None` for primitives natively (currently
  documented as "complex → JSON-decode"). Adds a schema-dump
  truncation contract. Relocates `compute_schema` from
  `packages/testing/` to `packages/cli/`.
- `module-layout-discipline`: requires `tests/packages/<name>/`
  uniformly contains an `__init__.py`, with a documented exception
  mechanism (importlib mode or rename) for stdlib-name collisions.
  Splits `packages/lint/static.py` into per-family rule modules under
  `packages/lint/rules/` — file-count budget for that subpackage
  ≤ 6 files.

## Impact

- **Affected code**: `src/a2kit/packages/{cli,mcp,testing,lint,otel}/`,
  `tests/packages/{lint,mcp,select,otel}/`, `examples/tracker/`,
  `examples/streaming_logger/` (new), `pyproject.toml`,
  `Makefile`, `README.md`, `ANTIPATTERNS.md`, `CHANGELOG.md`.
- **APIs**: `_APP_CTX` and `compute_schema` import paths shift; the
  current locations remain as compatibility re-exports for one cycle
  (no runtime breakage).
- **Dependencies**: `[project.optional-dependencies] otel = [...]`
  added; `ty>=0.0.34` restored to dev deps; `opentelemetry-{api,sdk}`
  added to dev deps for OTel test coverage.
- **CI**: `make lint` becomes a hard gate (ruff + ty + a2kit lint
  static); `--cov-fail-under=95` reinstated once the bar is met.
- **Tag readiness**: with this change merged, v1.0.0 tag has no
  outstanding "known debt" markers.
