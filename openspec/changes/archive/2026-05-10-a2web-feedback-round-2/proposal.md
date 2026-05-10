## Why

a2web's `A2KIT_FEEDBACK.md` (round 1, 11 items + 6 open questions) drove the v0.24 release: lifespan hooks, singletons, sync resolve, optional `connection`, the LDD free-function refactor + typed event registry, the `A2K-LOCAL-RETURN-MODEL` lint, and `a2kit.testing.peek`. Six items remain open after v0.24, four of them in the original Tier-1/Tier-2 priority bands the consumer flagged as highest-leverage. This change addresses those remaining items and converts the six open questions into documented contracts.

The biggest remaining hole — **no in-process test client** — affects every a2kit-using app, not just a2web. Every consumer today bypasses the dispatcher and tests implementation modules directly, leaving the adapter layer (DI resolution, schema discovery, ToolContext wiring, output rendering, error envelope) untested. Shipping a test client is a quality multiplier across the ecosystem.

## What Changes

- **Add `a2kit.testing.client(app)`** — async-context-manager harness that runs the full dispatcher in-process. Captures events/progress for assertion. Lifecycle hooks fire. Renders responses for wire-format checks.
- **Extend verb decorators with MCP annotations** — `@a2kit.read(idempotent=..., open_world=..., title=...)` and `@a2kit.write(destructive=..., title=...)`. Forwarded to FastMCP `ToolAnnotations` on the MCP path; ignored on CLI. Conservative defaults.
- **Add `a2kit.health` module** — `App(..., health_tool=True)` registers a `_meta.health` tool; `@app.health_check` decorator collects readiness probes. Hidden from `list_tools` by default. CLI `<app> health` exits non-zero on degraded.
- **Document the docstring contract** — first line is the description; full body becomes the long help. Markdown supported and rendered raw on MCP / stripped on CLI. Add a `Param(description=...)` annotation marker for kwarg docs.
- **Broaden antipattern #1 lint** — `_check_return` currently only catches `-> str`. Extend to all primitives (`int`/`float`/`bool`/`bytes`) and `None` — tools must return a `BaseModel` or `dict[str, Any]` shape (or a list/Page of such).
- **Document open questions Q1–Q6** — write a short "Operational contracts" doc covering cancellation propagation (anyio cancellation flows through the dispatcher; tools MUST handle `CancelledError`), per-tool timeout (not built-in; pattern recommendation), multi-App support (production-supported; lifespan composes per-App), dev auto-reload (not in scope; pattern), error envelope (MCP `JsonRpcError` / CLI exit code + message), streaming output (not in v0.24; deferred).

Item 11 (fluent-builder hygiene) is **deferred** — significant API surface change with no consumer blocker today; would split into its own change after broader consumer survey.

## Capabilities

### New Capabilities
- `in-process-test-client`: Test harness that invokes tools through the full dispatcher (DI, decorators, rendering) and captures events/progress/output for assertion.
- `mcp-tool-annotations`: Pass-through of MCP `ToolAnnotations` (idempotent, openWorld, destructive, title) via verb decorators.
- `health-probe`: Built-in health/ping tool with user-extensible readiness checks.
- `tool-description-contract`: Documented mapping from docstrings + `Param` annotations to MCP tool/parameter descriptions and CLI `--help`.
- `operational-contracts`: Documented behaviors for cancellation, multi-App, errors, and streaming.

### Modified Capabilities
- `tool-return-type-discipline`: Broaden the decoration-time return-type guard from `-> str` to all primitive returns and `None`.
- `verb-decorators`: Add MCP annotation kwargs to `@read` / `@write` / `@tool`.

## Impact

- **API**: New `a2kit.testing.client` async-context-manager. New kwargs on verb decorators. New `App(..., health_tool=...)` constructor flag. New `@app.health_check` decorator. New `a2kit.Param` annotation marker.
- **Code**: ~600 LOC new (test client ~250, health ~80, MCP annotations ~30, docstring resolution ~50, lint extension ~20, docs ~150).
- **Behavioral**: Conservative annotation defaults — no existing tools change wire output unless they opt in. Health tool registered only when explicitly requested.
- **Backwards compat**: Additive. Old code keeps working. Antipattern #1 lint broadening is a strict tightening — apps returning `-> int` etc. will now fail at decoration time; documented as breaking-on-import in the changelog (pre-1.0 latitude).
- **Cold start**: No regression. Test client lazy-loads when `a2kit.testing.client` is accessed. Health module lazy-loads via the existing `__getattr__` pattern.
- **Docs**: README gets a "Testing" section, an "MCP annotations" section, and an "Operational contracts" appendix.
