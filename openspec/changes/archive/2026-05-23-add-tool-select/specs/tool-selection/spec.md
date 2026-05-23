## ADDED Requirements

### Requirement: `--select EXPR` filters the runtime registry at build time

The `serve` CLI SHALL accept a repeatable `--select EXPR` option. Each `EXPR` SHALL be a key=value selector parsed by `a2kit.packages.select.compile_selector`. Multiple `--select` flags SHALL be ANDed when applied. The filter SHALL be applied during `App.build(select=...)` and frozen on the resulting `AppRuntime`. Per-call dispatch SHALL NOT re-evaluate selectors.

#### Scenario: Read-only mode hides write tools

- **GIVEN** an `App` with `@app.read async def fetch(...)` and `@app.write async def upsert(...)`
- **WHEN** the app is started with `serve --transport=http --select 'verb=read,list'`
- **THEN** the FastMCP `tools/list` response contains `fetch` but not `upsert`
- **AND** `POST /api/upsert` returns 404

#### Scenario: Multiple --select flags AND together

- **GIVEN** an `App` with three tools: `t1` (verb=read, tag=public), `t2` (verb=read, tag=internal), `t3` (verb=write, tag=public)
- **WHEN** the app is started with `serve --select 'verb=read' --select 'tag=public'`
- **THEN** only `t1` is exposed
- **AND** `t2` (wrong tag) and `t3` (wrong verb) are both filtered out

### Requirement: DSL syntax `category=value1,value2,!value3`

The selector DSL SHALL parse expressions of the form `category=values` where:

- `category` is one of `verb`, `name`, `surface`.
- `values` is a comma-separated list. Each value is either a plain token (include) or a `!`-prefixed token (exclude).
- Whitespace around tokens is stripped.
- The reserved character set is `=` (separator), `,` (value separator), `!` (leading-only negation prefix). These characters SHALL NOT appear inside a value.
- When the include set is empty, the include check passes vacuously; otherwise the descriptor's attribute must be in the include set. The exclude check always runs.

A name value SHALL be matched using `fnmatch.fnmatchcase` (shell-style glob). `verb` matches by string equality against `descriptor.verb`. `surface` accepts only the values `mcp` and `api`; any other value raises `SelectorError`.

#### Scenario: Name glob with negation

- **GIVEN** an `App` with tools `fetch_user`, `fetch_session`, `internal_fetch_diagnostics`
- **WHEN** the app is started with `serve --select 'name=fetch_*,!internal_*'`
- **THEN** `fetch_user` and `fetch_session` are exposed
- **AND** `internal_fetch_diagnostics` is filtered out

#### Scenario: Exclude-only selector

- **GIVEN** tools `t1`, `t2`, `t3` (all `verb=read`)
- **WHEN** the app is started with `serve --select 'name=!t3'`
- **THEN** `t1` and `t2` are exposed (include set is empty so its check passes vacuously)
- **AND** `t3` is filtered out

#### Scenario: Surface accepts only mcp and api

- **WHEN** the user runs `serve --select 'surface=cli'`
- **THEN** the process exits with status 2
- **AND** stderr contains "surface accepts only 'mcp' or 'api'"

### Requirement: Selector parse errors raise SelectorError

`compile_selector` SHALL raise `SelectorError` (a `ValueError` subclass) on any parse problem. The CLI wrapper SHALL catch this, write a single-line error message naming the offending fragment to stderr, and exit with code 2.

#### Scenario: Missing `=`

- **WHEN** the user runs `serve --select 'verb read'`
- **THEN** the process exits with status 2
- **AND** stderr contains "selector must be 'category=values'" and the offending expression

#### Scenario: Unknown category

- **WHEN** the user runs `serve --select 'rooter=memories'`
- **THEN** the process exits with status 2
- **AND** stderr contains "unknown category 'rooter'; expected verb|name|tag|surface"

#### Scenario: Empty value

- **WHEN** the user runs `serve --select 'verb='`
- **THEN** the process exits with status 2
- **AND** stderr contains "empty value" and the offending expression

### Requirement: `App.build(select=...)` accepts a list of selector expressions

The `build()` function SHALL accept `select: list[str] | None = None`. When non-empty, each string is compiled via `compile_selector` and applied to filter `app._tools`, `app._api_routes`, and `app._mcp_features` before constructing `AppRuntime`. ANDed semantics across selectors apply.

`select=None` and `select=[]` SHALL both pass through unfiltered.

#### Scenario: Programmatic build with selector

- **GIVEN** an `App` and a test wanting only read tools
- **WHEN** `build(app, select=["verb=read"])` is called
- **THEN** the returned `AppRuntime`'s tools registry contains only read tools
- **AND** subsequent serve operations expose only those tools

### Requirement: Selector freeze; no per-call cost

Selector compilation and application SHALL occur exactly once per `App.build()` call. The dispatch pipeline SHALL NOT invoke `Selector.matches` during tool invocation. Filtered registries are immutable on `AppRuntime`.

#### Scenario: Dispatch hot path is selector-free

- **WHEN** a tool is dispatched after a filtered build
- **THEN** the dispatch path does not call any `Selector.matches` or `compile_selector`
- **AND** the dispatch latency is identical to an unfiltered build (within measurement noise)
