## Why

Operators need to deploy a single a2kit codebase in restricted modes — read-only audits, MCP-only deployments of mixed apps, demo environments exposing a subset of tools by name. Today a2kit has no runtime filter; ops must edit the codebase or build separate entry points. A small shell-friendly DSL (no CEL) covers the stated needs (read-only mode, specific tools by name, surface-only deploys) without adding a dependency, an expression language, or a per-request evaluation cost.

**Depends on `add-multi-surface`**: requires the `verb`, `expose` fields on `ToolDescriptor` and the `surface-auto-mount` capability. `add-multi-surface` must archive before this change validates.

## What Changes

- New CLI flag `--select EXPR` on the `serve` subcommand, repeatable. Multiple `--select` flags AND together. Frozen at `App.build(select=...)` time on `AppRuntime`.
- New package `src/a2kit/packages/select/` with `compile_selector(expr) -> Selector` and `Selector.matches(descriptor) -> bool`. Stdlib only.
- DSL syntax: `category=value1,value2,!value3`. Categories: `verb` (matches `descriptor.verb`), `name` (glob via `fnmatch` against `descriptor.name`), `surface` (Literal values `mcp` / `api`, matches against `descriptor.expose`). Negation with `!` prefix. Positive values within a category are OR; `!` values are AND-NOT.
- `App.build(select: list[str] | None = None)` accepts compiled selectors. Filters `tools`, `api_routes`, `mcp_features` registries through ANDed selectors before producing `AppRuntime`.
- `surface=` category interacts with the `surface-auto-mount` capability (from `add-multi-surface`): if filtering leaves a substrate with zero registrations, that mount is skipped — same auto-mount rule, applied after filter.
- Selector parse errors raise `SelectorError` at CLI parse time, exit code 2, with a message naming the offending fragment.
- CEL expressions and `tag=` category are NOT introduced (parked in design.md as future enhancements). `tag=` is deferred because a2kit has no author-supplied tagging surface today — verb tags are framework-stamped and would be redundant with `verb=`.

## Capabilities

### New Capabilities

- `tool-selection`: A key=value DSL for filtering which tools, routes, and MCP features a process exposes. Compiled at `App.build()` time, applies uniformly across every substrate the process serves.

### Modified Capabilities

- `surface-auto-mount`: Add post-filter rule — auto-mount runs after the selector filter; substrates with zero remaining registrations are not mounted, regardless of whether they had registrations before filtering. This makes `--select 'surface=mcp'` the structural answer to "disable the FastAPI mount for this deploy."

## Impact

**Source code**:
- New: `src/a2kit/packages/select/__init__.py` with `compile_selector`, `Selector`, `SelectorError` (~50 LOC total, stdlib-only)
- Modified: `src/a2kit/runtime.py` — `build(app, select=...)` signature update; filtered registry construction
- Modified: `src/a2kit/packages/cli/builder.py` — add `--select` typer option, repeatable, wired into `serve` callback

**Dependencies**:
- None. `fnmatch` (stdlib) handles globbing.

**Tests**:
- New: `tests/packages/select/test_compile.py` — parser edge cases (happy path + errors + negation in one file)
- New: `tests/packages/select/test_evaluator.py` — matching against `ToolDescriptor` fixtures (verb / name / surface in one file)
- New: `tests/packages/select/test_integration.py` — full-multiplex serve scenarios (read-only mode + parameterized surface-only)

**Docs**:
- New: `docs/SELECT.md` — DSL reference with 5+ worked examples
- Updated CLI `--help` text linking to the DSL doc

**Consumers**:
- No existing consumer uses `--select` (the flag is new). Authors writing tools see no API change unless they want to opt into filtering at build time via `App.build(select=...)`.
