## ADDED Requirements

### Requirement: FastMCP is a hard dependency; a2kit does not reinvent its primitives

The library SHALL declare `fastmcp>=3.2,<4` as a required dependency in `pyproject.toml`. Where FastMCP ships an equivalent primitive, a2kit SHALL NOT ship its own.

#### Scenario: FastMCP is required, not optional
- **WHEN** `pyproject.toml [project] dependencies` is inspected
- **THEN** `fastmcp` appears with version constraint `>=3.2,<4`

#### Scenario: a2kit DI is delegated
- **WHEN** the source tree is inspected after the change
- **THEN** no `src/a2kit/di.py` exists; users import `Depends` and `Dependency` from `fastmcp` directly. a2kit does NOT re-export them.

#### Scenario: a2kit middleware chain is delegated
- **WHEN** the source tree is inspected after the change
- **THEN** no chain-assembling code remains in core; concrete a2kit-unique middlewares subclass `fastmcp.server.middleware.Middleware` and are registered via `server.add_middleware(...)`

#### Scenario: FastMCPLike Protocol deleted
- **WHEN** the source tree is inspected after the change
- **THEN** no `FastMCPLike` Protocol exists; references to `FastMCP` use the concrete `FastMCP` class

### Requirement: a2kit does not re-export external library symbols

a2kit SHALL NOT re-export symbols owned by external libraries (FastMCP, the MCP SDK, `uncalled_for`, structlog, OTel, cel-python, vcrpy, syrupy, pydantic-settings, etc.). Users import external symbols directly from the owning library. a2kit's public surface contains only what a2kit owns.

#### Scenario: No FastMCP re-exports
- **WHEN** `a2kit/__init__.py` is inspected
- **THEN** it does NOT export `Depends`, `Dependency`, `Shared`, `SharedContext`, `Context`, `CurrentContext`, `CurrentFastMCP`, `Middleware`, or any other FastMCP/`uncalled_for` symbol

#### Scenario: No MCP SDK re-exports
- **WHEN** `a2kit/__init__.py` is inspected
- **THEN** it does NOT export `ToolAnnotations` or any other `mcp.types` symbol

#### Scenario: No structlog/OTel/etc. re-exports
- **WHEN** `a2kit/__init__.py` and any plugin package's `__init__.py` are inspected
- **THEN** they export only symbols defined in their own source files; no `from structlog import ...`, `from opentelemetry import ...`, `from cel-python import ...`, etc., re-exports

#### Scenario: a2kit's public surface contains only what a2kit owns
- **WHEN** an external symbol is needed in user code
- **THEN** the user imports it from the owning library directly (e.g. `from fastmcp import Depends`, not `from a2kit import Depends`)

### Requirement: Verb decorators map to MCP `ToolAnnotations` + tags

`@a2kit.read`, `@a2kit.write`, and `@a2kit.list` SHALL be thin sugar over `FastMCP.tool(annotations=ToolAnnotations(...), tags=...)`. Each verb decorator SHALL be implementable in ≤ 10 lines.

#### Scenario: read maps to readOnlyHint=True
- **WHEN** a function is decorated with `@a2kit.read`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=True, destructiveHint=False)` (or equivalent semantic)

#### Scenario: write maps to readOnlyHint=False, destructiveHint=True
- **WHEN** a function is decorated with `@a2kit.write`
- **THEN** the underlying FastMCP tool registration receives `ToolAnnotations(readOnlyHint=False, destructiveHint=True)` (or equivalent semantic)

### Requirement: Capabilities map to FastMCP `tags`

a2kit's capability tagging system SHALL use FastMCP's native `tags: set[str]` parameter on `tool()`. The `Cap` enum (or equivalent registry) SHALL produce string tags compatible with FastMCP's tag system.

#### Scenario: Capability tag round-trips
- **WHEN** a tool is decorated with a capability `Cap.WRITE`
- **THEN** the registered FastMCP tool's `tags` set contains the corresponding string token

#### Scenario: Select grammar filters by FastMCP tags
- **WHEN** a `--select` expression evaluates against the registered tools
- **THEN** the evaluator reads `tags` from FastMCP's tool registry, not from a separate a2kit metadata store

### Requirement: In-house select grammar replaced by cel-python directly

The library SHALL NOT ship its own filter / select grammar. Selection SHALL be delegated to **cel-python** with user-facing CEL syntax (`&&` / `||` / `!`, field-access atoms).

#### Scenario: Select grammar modules deleted
- **WHEN** the source tree is inspected after the change
- **THEN** no module named `_select`, `_select_parse`, `_select_eval`, or `projection` exists under `src/a2kit/`

#### Scenario: cel-python is a required dependency
- **WHEN** `pyproject.toml` is inspected
- **THEN** `cel-python` appears under `[project] dependencies` (or as a required marker for `packages/select/`); it does NOT appear under `[project.optional-dependencies]` named `[projection]`

#### Scenario: User-facing grammar is real CEL
- **WHEN** a user writes a `--select` expression after the migration
- **THEN** they use real CEL syntax (`&&` / `||` / `!`, field-access atoms like `tool.foo` / `cap.foo` / `surface.mcp`)

#### Scenario: CEL migration recipe shipped
- **WHEN** a downstream consumer reads the v1.0 CHANGELOG
- **THEN** they find a translation table mapping every legacy atom form to its CEL equivalent

### Requirement: Thin core + plugin packages structure

The package SHALL be organized into a thin core at `src/a2kit/*.py` (top-level files only) and plugin packages under `src/a2kit/packages/<name>/`. a2kit core SHALL function without importing any plugin package.

#### Scenario: Core is at top level
- **WHEN** `ls src/a2kit/*.py` is run after the change
- **THEN** the result is the core file list (`app.py`, `tool.py`, `signature.py`, `metadata.py`, `routers.py`, `runner.py`, `cli.py`, `capabilities.py`, `exceptions.py`, plus `__init__.py`)

#### Scenario: Plugin packages live under packages/
- **WHEN** `ls src/a2kit/packages/` is run after the change
- **THEN** the result lists at most: `connections`, `enrichers`, `select`, `formatter`, `middlewares`, `testing`, `lint` (plus `__init__.py`)

#### Scenario: Core works without plugins
- **WHEN** an MCP author imports from `a2kit` (top level only) and never references `a2kit.packages.*`
- **THEN** they can register tools, run the CLI, compose an `App`, and serve over MCP without errors

### Requirement: Lint moves to packages/lint/ and flattens

The `a2kit.lint` package SHALL move to `a2kit.packages.lint` and SHALL flatten from 11 files to at most 3 (`static.py`, `runtime.py`, `cli.py`). The `a2kit` console script SHALL relocate to `a2kit.packages.lint.cli:main`.

#### Scenario: Lint at packages/lint
- **WHEN** the source tree is inspected after the change
- **THEN** `src/a2kit/packages/lint/` exists with at most 3 source files (plus `__init__.py`); `src/a2kit/lint/` does not exist

#### Scenario: Console script relocated
- **WHEN** `pyproject.toml [project.scripts]` is inspected
- **THEN** `a2kit = "a2kit.packages.lint.cli:main"` is present

### Requirement: Scaffold namespace is flattened into core

The `a2kit.scaffold` namespace SHALL be deleted. Its contents (`Router`, `RouterRegistry`, `MCPRunner`, `RunnerOptions`, `build_cli`, `register_ephemeral_connections`, `RegisterBlock`) SHALL move to top-level `routers.py`, `runner.py`, `cli.py`. `scope_filter` and the ephemeral / filtered store wrappers SHALL move to `packages/connections/`.

#### Scenario: Scaffold directory deleted
- **WHEN** the source tree is inspected after the change
- **THEN** no `src/a2kit/scaffold/` directory exists

#### Scenario: Composition primitives live at top level
- **WHEN** an author imports `Router`, `MCPRunner`, or `build_cli`
- **THEN** the symbols are importable from `a2kit` directly, or from top-level modules `a2kit.routers`, `a2kit.runner`, `a2kit.cli`

### Requirement: contrib namespace is deleted

The `a2kit.contrib` namespace SHALL be removed entirely. Its only contents (`a2kit.contrib.connections.get_conn_factory` and helpers) SHALL move to `a2kit.packages.connections`.

#### Scenario: contrib directory deleted
- **WHEN** the source tree is inspected after the change
- **THEN** no `src/a2kit/contrib/` directory exists

### Requirement: ConnectionConfig adopts pydantic-settings (Contract B)

`a2kit.packages.connections.ConnectionConfig` SHALL inherit from `pydantic_settings.BaseSettings`. Field values containing `${VAR}` placeholders OR `op://` references SHALL be resolved **eagerly at configuration load time**, not lazily at API-call time. Loading a connection with an unset env var or unreachable secret SHALL fail at `store.load(...)`, not at first tool call.

#### Scenario: ${VAR} resolved at load
- **WHEN** a connection TOML stores `token = "${MY_TOKEN}"` and `MY_TOKEN` is set
- **THEN** `store.load(...)` returns a config whose `.token` is the real value of `MY_TOKEN`

#### Scenario: Missing env var fails at load
- **WHEN** a connection TOML stores `token = "${MISSING_VAR}"` and `MISSING_VAR` is unset
- **THEN** `store.load(...)` raises a typed error before any tool runs

#### Scenario: pydantic-settings is a required dependency
- **WHEN** `pyproject.toml` is inspected after the change
- **THEN** `pydantic-settings` appears under `[project] dependencies` (or required for `packages/connections/`)

#### Scenario: Cloud secret backend usable via pydantic-settings source
- **WHEN** a downstream MCP wants to source secrets from AWS/Azure/GCP Secrets Manager
- **THEN** they configure `ConnectionConfig.model_config` with the relevant pydantic-settings source — no a2kit-specific resolver registration needed

### Requirement: DI uses uncalled_for parameter-default form

Tool function signatures SHALL declare DI dependencies via `uncalled_for`'s parameter-default form: `*, name: T = Depends(factory)`. The `Annotated[T, Depends(fn)]` form SHALL NOT be used for value injection.

#### Scenario: Tool fns use parameter-default Depends
- **WHEN** a tool function declares a DI dependency
- **THEN** the parameter signature is `*, name: T = Depends(factory)`, not `*, name: Annotated[T, Depends(factory)]`

#### Scenario: Depends imported from uncalled_for
- **WHEN** any source file imports `Depends`
- **THEN** the import path is `from uncalled_for import Depends`

#### Scenario: a2kit ships no di.py
- **WHEN** the source tree is inspected after the change
- **THEN** no `src/a2kit/di.py` exists

### Requirement: A2K-DI lint rules catch misuse

The lint subsystem SHALL flag the following patterns:

- **A2K-DI-ANNOTATED**: `Annotated[T, Depends(fn)]` in a tool fn signature.
- **A2K-DI-IMPORT-LEGACY**: `from a2kit.di import Depends`.
- **A2K-DI-IMPORT-SLOW**: `from fastmcp.dependencies import Depends`.
- **A2K-DI-KWONLY**: tool fn DI parameters declared as positional.

#### Scenario: Annotated misuse caught
- **WHEN** lint analyzes a fn with `Annotated[T, Depends(fn)]` parameter
- **THEN** A2K-DI-ANNOTATED fires with a hint to use parameter-default form

#### Scenario: Slow import path flagged
- **WHEN** lint sees `from fastmcp.dependencies import Depends`
- **THEN** A2K-DI-IMPORT-SLOW fires with the cold-start cost rationale

### Requirement: Single-entry `a2kit.run(app)` dispatches all modes

The library SHALL expose a top-level `a2kit.run(app)` function that, given an `App`, builds a Click group dispatching all modes (per-Router tool subcommands, `connections`, `schema`, `serve`) based on argv. The user's package SHALL need only one console-script entry pointing at a function that calls `a2kit.run(app)`.

#### Scenario: Single console-script entry covers all modes
- **WHEN** a user installs a tracker MCP via `uvx tracker`
- **THEN** they can invoke `tracker --help`, `tracker tasks list-tasks ...`, `tracker connections login ...`, `tracker schema`, and `tracker serve` from the same console script

#### Scenario: `serve` is the only command that imports fastmcp
- **WHEN** a user runs any non-serve command (`--help`, a tool, `connections`, `schema`)
- **THEN** `'fastmcp' not in sys.modules` after the command completes

#### Scenario: `App` has no `run` / `run_server` / `run_async` methods
- **WHEN** the source tree is inspected after the change
- **THEN** the `App` class has no `run`, `run_server`, or `run_async` method; users invoke `a2kit.run(app)` instead

### Requirement: `build_mcp_server` forwards FastMCP kwargs

`a2kit.packages.mcp.build_mcp_server(app, **fastmcp_kwargs)` SHALL accept arbitrary keyword arguments and forward them to `FastMCP.__init__`. This includes (but is not limited to) `auth`, `providers`, `transforms`, `lifespan`, `tasks`, and any future FastMCP plugin parameters. a2kit SHALL NOT ship its own auth abstraction.

#### Scenario: Auth provider forwards transparently
- **WHEN** a user calls `build_mcp_server(app, auth=GoogleAuthProvider(...))`
- **THEN** the resulting FastMCP server has the auth provider installed; no a2kit-side wrapping or translation occurs

#### Scenario: Future FastMCP plugins work without a2kit changes
- **WHEN** FastMCP introduces a new `__init__` parameter
- **THEN** users can pass it via `build_mcp_server(app, new_param=...)` without any a2kit code changes

### Requirement: ToolContext Protocol provides protocol-neutral logging + progress

The library SHALL ship a `ToolContext` Protocol in `a2kit/runtime.py` exposing `info`, `warning`, `error`, `debug` (sync), and `report_progress` (async) methods. Tool functions that need logging or progress reporting SHALL declare a `ctx: ToolContext` keyword-only parameter. Both adapters SHALL detect this parameter and supply an implementation at invocation time:

- MCP adapter SHALL wrap `fastmcp.Context` to fulfill the Protocol; logs and progress events flow over the MCP wire.
- CLI adapter SHALL print to stderr in compact key=value text format (LLM-friendly); progress reports as inline status lines.

a2kit SHALL NOT depend on `structlog` for the CLI Context implementation.

#### Scenario: ToolContext usable in both MCP and CLI invocations
- **WHEN** a tool fn declares `ctx: ToolContext` and calls `ctx.info("msg", k=v)`
- **THEN** the message is delivered to the MCP wire (in serve mode) OR printed to stderr (in CLI mode), without modification of the tool fn

#### Scenario: ctx parameter excluded from input schema
- **WHEN** a tool fn has both `ctx: ToolContext` and other kwonly params
- **THEN** the `--schema` output and Click subcommand options do NOT include `ctx`

#### Scenario: CLI Context emits compact text, not JSON
- **WHEN** a CLI invocation triggers `ctx.info("starting", file="x")`
- **THEN** stderr receives a single line like `[INFO] starting file=x`

#### Scenario: No structlog dependency
- **WHEN** the `packages/cli/` source tree is inspected
- **THEN** no module imports `structlog`

### Requirement: Enrichers are protocol-neutral; both MCP and CLI honor them

`packages/enrichers/` SHALL ship a generic `wrap(fn, enricher)` helper that wraps a tool function with try/except → enricher transform. Both the MCP adapter (`packages/mcp/build_mcp_server`) and the CLI adapter (`packages/cli/build_cli`) SHALL apply this wrapping when registering tools. Enrichers SHALL NOT be implemented as FastMCP `Middleware` subclasses.

#### Scenario: Enricher fires identically for MCP and CLI invocations
- **WHEN** a tool fn declared with an `enricher=` decorator argument raises an exception
- **THEN** the enricher transforms the exception identically whether invoked via `tracker tasks list-tasks` (CLI) or `tracker serve` (MCP)

#### Scenario: No enricher Middleware subclass exists
- **WHEN** the source tree is inspected after the change
- **THEN** no file under `packages/middlewares/` named `enricher.py` (or similar) exists; the enricher logic lives in `packages/enrichers/`

### Requirement: CLI tool output flows through the formatter

`packages/cli/` SHALL invoke tools in-process and pass the raw return value through `packages/formatter/format_response` before printing to stdout. Tool subcommands SHALL accept a `--format=auto|tsv|toon|json` flag (default `auto` — uses the TSV/TOON/JSON heuristic).

#### Scenario: CLI output matches MCP wire format
- **WHEN** the same tool is invoked via CLI (`tracker tasks list-tasks ...`) and via MCP (`tracker serve` + a client call)
- **THEN** the rendered payload is byte-identical when both use `--format=auto` (or the agent's default)

#### Scenario: User can override format
- **WHEN** a user runs `tracker tasks list-tasks --format=json`
- **THEN** the output is JSON regardless of the auto-heuristic verdict

### Requirement: Schema discovery surface

The CLI SHALL expose tool schemas in two ways:

- **Per-tool `--schema` flag**: every tool subcommand SHALL accept `--schema` to print the tool's MCP-shaped JSON schema and exit.
- **Top-level `schema` command**: `<app> schema [TOOL_NAME] [--jsonl]` prints schemas for all tools (or one) as JSON.

Schema generation SHALL be pure-Python (pydantic + typing), MUST NOT load fastmcp, and MUST use the same code path that powers the per-tool snapshot test fixture.

#### Scenario: --schema on a tool prints JSON
- **WHEN** a user runs `<app> <router> <tool> --schema`
- **THEN** stdout contains a JSON object with at least `name`, `description`, `inputSchema`, `outputSchema`, `annotations`, `tags`, `meta` fields

#### Scenario: Top-level `schema` lists all tools
- **WHEN** a user runs `<app> schema`
- **THEN** stdout contains a JSON object mapping every registered tool's name to its schema

#### Scenario: Schema discovery does not load fastmcp
- **WHEN** any schema-printing command completes
- **THEN** `'fastmcp' not in sys.modules`

#### Scenario: Test snapshot fixture reuses schema helper
- **WHEN** the test snapshot fixture writes per-tool snapshot files
- **THEN** the file contents are byte-identical to the output of `<app> <router> <tool> --schema --format=toon` for the same tool

#### Scenario: TOON is the default schema format
- **WHEN** a user runs `<app> schema [TOOL_NAME]` without `--format`
- **THEN** the output is TOON-encoded (token-efficient default for LLM consumers)

#### Scenario: JSON format opt-in
- **WHEN** a user runs `<app> schema [TOOL_NAME] --format=json`
- **THEN** the output is JSON (compatible with JSON Schema tooling, code generators, etc.)

### Requirement: CLI adapter provides progressive disclosure by Router

`a2kit.packages.cli.build_cli(app)` SHALL return a Click group with progressive disclosure:

- Top level: one Click subgroup per registered Router (slug from `Router.__name__`), plus a built-in `connections` subgroup.
- Each Router subgroup: one Click subcommand per registered tool (kebab-cased tool name).
- Each Router subgroup's `help` text SHALL include a hint pointing the user at the next level (e.g. *"(run `<app> <router>` for tools)"*).
- Each tool subcommand SHALL accept the tool's kwonly parameters as Click options (DI dependencies stripped via `uncalled_for.without_dependencies`).
- Tool subcommand body SHALL invoke the tool function in-process (no FastMCP server, no client roundtrip).

#### Scenario: Top-level lists Routers with hints
- **WHEN** a user runs the CLI with `--help` at the top level
- **THEN** they see one entry per registered Router (plus `connections`), each with a "run X for tools" hint

#### Scenario: Router subgroup lists tools
- **WHEN** a user runs `<app> <router> --help`
- **THEN** they see one entry per tool registered in that Router

#### Scenario: Tool subcommand exposes kwonly params, hides DI
- **WHEN** a user runs `<app> <router> <tool> --help`
- **THEN** they see one Click option per tool kwonly parameter, with DI dependencies hidden

#### Scenario: CLI invocation does not import fastmcp
- **WHEN** a user runs any CLI command (lint, connections, or a tool)
- **THEN** `fastmcp` does NOT appear in `sys.modules` after the command completes

### Requirement: Logging wrapper deleted

The `a2kit.logging` wrapper module SHALL be deleted. Documentation SHALL instruct users to use **structlog** directly. a2kit SHALL NOT ship a `tool.name` / `connection.key` auto-binding helper.

#### Scenario: logging.py absent
- **WHEN** the source tree is inspected after the change
- **THEN** no `src/a2kit/logging.py` exists

### Requirement: Testing wrappers reduced to thin fixtures

`a2kit.testing` + `_cassette.py` + schema-snapshot wrappers SHALL be removed. `packages/testing/` SHALL contain only thin pytest fixtures + light glue for vcrpy + syrupy.

#### Scenario: Cassette wrapper removed
- **WHEN** the source tree is inspected after the change
- **THEN** no `_cassette.py` module exists anywhere under `src/a2kit/`

#### Scenario: Docs reference syrupy and vcrpy directly
- **WHEN** a user reads documentation for testing MCP tools
- **THEN** examples invoke vcrpy and syrupy APIs directly, not a2kit wrappers

### Requirement: Test override pattern uses uncalled_for primitives

The pre-refactor `app.dependency_overrides[fn] = fake_fn` pattern SHALL be replaced by `uncalled_for.resolved_dependencies(fn, kwargs={...})` for inline injection or rebuilt fns with `Depends(fake_factory)` for module-level swap. a2kit SHALL NOT ship its own override-map abstraction.

#### Scenario: dependency_overrides removed
- **WHEN** the source tree is inspected after the change
- **THEN** no `dependency_overrides` attribute appears on `App` or any a2kit class

#### Scenario: Test fixtures use uncalled_for primitives
- **WHEN** a test fixture in `packages/testing/` sets up DI for a tool under test
- **THEN** it uses `uncalled_for.resolved_dependencies` or rebuilds the tool fn with a fake `Depends(...)`, not an a2kit-specific override map

### Requirement: No backwards compatibility shims

The library SHALL ship no v0.x compat shims, deprecated aliases, or "removed in next cycle" carryovers. v1.0 is a clean break.

#### Scenario: No deprecated aliases
- **WHEN** the source tree is grepped for `DeprecationWarning`
- **THEN** no a2kit-emitted DeprecationWarnings exist

#### Scenario: No alias re-exports for renamed symbols
- **WHEN** a renamed symbol (e.g. `ConnectionConfig` formerly `ConnectionInfo`) is searched
- **THEN** only the new name exists in the source; the old name is not aliased
