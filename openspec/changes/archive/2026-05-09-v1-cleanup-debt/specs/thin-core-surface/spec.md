## ADDED Requirements

### Requirement: `App.use_factory` binds Depends factories to a stable identity

`a2kit.App` SHALL expose a `use_factory(factory, *, as_)` method that binds
a factory callable under a stable callable identity. Tools declaring
`Depends(as_)` SHALL resolve through the bound `factory` at invocation time.

#### Scenario: Factory binding propagates through `Depends`
- **WHEN** a tool fn declares `*, conn: T = Depends(get_conn)` and the App is configured with `app.use_factory(factory, as_=get_conn)`
- **THEN** invoking the tool resolves `conn` via `factory(...)` instead of `get_conn(...)`

#### Scenario: No module-level mutable slot pattern
- **WHEN** the canonical `examples/tracker/` is inspected
- **THEN** the example does NOT use `_impl: Callable | None = None` plus `set_get_conn(...)` to wire dependencies; it uses `app.use_factory(...)` instead

### Requirement: CLI option synthesis maps nullable primitives to native Click types

`a2kit.packages.cli` SHALL map parameter annotations of the form
`Optional[T]`, `T | None`, `Union[T, None]` for primitive `T ∈ {int, float, str, bool}`
to the corresponding native Click type with `default=None` and
`required=False`. Such parameters SHALL NOT fall through to JSON-decode mode.

#### Scenario: `Optional[int]` produces an integer option
- **WHEN** a tool declares `*, project_id: int | None = None`
- **THEN** the generated CLI subcommand exposes `--project-id INTEGER` (Click's `IntType`); no JSON parsing happens at call time

#### Scenario: `str | None` produces a string option
- **WHEN** a tool declares `*, query: str | None = None`
- **THEN** the generated CLI subcommand exposes `--query TEXT`; the value is forwarded as-is

#### Scenario: Non-primitive nullable still JSON-decodes
- **WHEN** a tool declares `*, items: list[int] | None = None`
- **THEN** the generated CLI option remains JSON-decoded (consistent with current complex-type handling)

### Requirement: Schema dump output respects character cap

The `<app> schema [TOOL]` command output SHALL pass through the formatter's
`truncate(...)` helper. If the encoded payload exceeds the configured cap
(default: 50,000 characters), output SHALL end with a
`... (truncated)` marker.

#### Scenario: Large schema produces truncated output
- **WHEN** the user runs `<app> schema` against an app whose combined schema dict encodes to over 50,000 characters
- **THEN** stdout ends with the truncation marker; exit code is 0

## MODIFIED Requirements

### Requirement: Schema discovery surface

The CLI SHALL expose tool schemas in two ways:

- **Per-tool `--schema` flag**: every tool subcommand SHALL accept `--schema`
  to print the tool's MCP-shaped JSON schema and exit.
- **Top-level `schema` command**: `<app> schema [TOOL_NAME] [--jsonl]` prints
  schemas for all tools (or one) as JSON.

Schema generation SHALL be pure-Python (pydantic + typing), MUST NOT load
fastmcp, and MUST use the same code path that powers the per-tool snapshot
test fixture.

The schema-generation helper `compute_schema(fn)` SHALL live at
`a2kit.packages.cli.schemas` (NOT at `a2kit.packages.testing.snapshots`).
The testing-snapshot helper imports from there. Output flows through the
formatter and respects the truncation cap.

#### Scenario: --schema on a tool prints JSON or TOON via formatter
- **WHEN** a user runs `<app> <router> <tool> --schema`
- **THEN** stdout contains the formatted schema (TOON by default, or
  JSON via `--format=json`) with at least `name`, `description`,
  `inputSchema`, `outputSchema`, `annotations`, `tags`, `meta` fields

#### Scenario: `compute_schema` lives in cli, not testing
- **WHEN** the source tree is inspected
- **THEN** `a2kit.packages.cli.schemas.compute_schema` is the canonical
  definition; `a2kit.packages.testing.snapshots` imports it from there

#### Scenario: Top-level `schema` lists all tools
- **WHEN** a user runs `<app> schema`
- **THEN** stdout contains a TOON-encoded mapping of every registered
  tool's name to its schema (or JSON when `--format=json`)

#### Scenario: Schema discovery does not load fastmcp
- **WHEN** any schema-printing command completes
- **THEN** `'fastmcp' not in sys.modules`

#### Scenario: Test snapshot fixture reuses schema helper
- **WHEN** the test snapshot fixture writes per-tool snapshot files
- **THEN** the file contents are byte-identical to the output of
  `<app> <router> <tool> --schema --format=toon` for the same tool
