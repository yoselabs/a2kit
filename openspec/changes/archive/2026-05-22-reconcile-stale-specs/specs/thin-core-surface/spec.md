## MODIFIED Requirements

### Requirement: FastMCP is a hard dependency; a2kit does not reinvent its primitives

The library SHALL declare `fastmcp` as a required dependency in `pyproject.toml`. Where FastMCP ships an equivalent primitive, a2kit SHALL NOT ship its own.

#### Scenario: FastMCP is required, not optional

- **WHEN** `pyproject.toml [project] dependencies` is inspected
- **THEN** `fastmcp` appears as a required dependency

#### Scenario: a2kit middleware chain is delegated

- **WHEN** the source tree is inspected
- **THEN** concrete a2kit-unique middlewares subclass `fastmcp.server.middleware.Middleware` and are registered through the FastMCP server

### Requirement: Thin core + plugin packages structure

The package SHALL be organized into a thin core at `src/a2kit/*.py` (top-level files only) and plugin packages under `src/a2kit/packages/<name>/`. a2kit core SHALL function without importing any plugin package. The specific set of core files and plugin packages is owned by the `module-layout-discipline` and `import-acyclicity` capabilities; this requirement asserts only the two-tier shape.

#### Scenario: Core works without plugins

- **WHEN** an MCP author imports from `a2kit` (top level only) and never references `a2kit.packages.*`
- **THEN** they can register tools, compose an `App`, and the core imports without pulling a plugin package

#### Scenario: Plugin packages live under packages/

- **WHEN** `ls src/a2kit/packages/` is run
- **THEN** the result lists the plugin packages, each a directory with its own `__init__.py`

### Requirement: No backwards compatibility shims

The library SHALL ship no compat shims, deprecated aliases, or "removed in next cycle" carryovers. A renamed symbol exists only under its new name; the old name is not aliased. The framework SHALL NOT emit `DeprecationWarning`.

#### Scenario: No deprecated aliases

- **WHEN** the source tree is grepped for `DeprecationWarning`
- **THEN** no a2kit-emitted `DeprecationWarning` exists

#### Scenario: No alias re-exports for renamed symbols

- **WHEN** a renamed symbol is searched
- **THEN** only the new name exists in the source; the old name is not aliased

## REMOVED Requirements

### Requirement: a2kit does not re-export external library symbols

**Reason**: This requirement enumerates a specific v1.0-era top-level surface (`A2KitMeta` → `a2kit.metadata`, `UNRESOLVED` → `a2kit.app`, named exception demotions, `LddSink` removal) that does not match the current `a2kit.__all__`. The top-level surface is owned by the current `__init__.py` and is not the v1.0 list this requirement freezes. A reconciled top-level-surface spec, if needed, is a follow-up; freezing a stale enumeration is worse than no requirement.

**Migration**: Consult `src/a2kit/__init__.py::__all__` for the actual top-level surface.

### Requirement: Verb decorators map to MCP `ToolAnnotations` + tags

**Reason**: This requirement is superseded by the `mcp-tool-annotations` capability, which specifies the verb-decorator-to-`ToolAnnotations` mapping in current terms. This requirement also names `@a2kit.list` (the verb is `@a2kit.list_`) and a "≤ 10 lines" implementation budget that is not a behavioral contract.

**Migration**: See the `mcp-tool-annotations` capability for the verb-decorator annotation mapping.

### Requirement: In-house select grammar replaced by cel-python directly

**Reason**: This requirement is a migration-era statement ("the library SHALL NOT ship its own filter grammar; selection SHALL be delegated to cel-python"). The select capability is owned by its own package (`packages/select/`); this requirement's scenarios police a one-time migration (modules deleted, CHANGELOG recipe shipped) that has long since completed and is not an ongoing contract.

**Migration**: Select/filter behavior is owned by the `packages/select/` package. There is no ongoing requirement here.

### Requirement: Lint moves to packages/lint/ and flattens

**Reason**: This requirement polices a one-time relocation ("`a2kit.lint` SHALL move to `a2kit.packages.lint` and flatten from 11 files to at most 3"). The relocation completed; lint now lives at `a2kit.packages.lint` with a `rules/` subpackage of per-family modules (see `module-layout-discipline`). The "at most 3 files" budget contradicts the current `rules/`-subpackage layout.

**Migration**: Lint layout is owned by the `module-layout-discipline` capability's "Lint rules split into per-family modules" requirement.

### Requirement: Scaffold namespace is flattened into core

**Reason**: This requirement polices a completed one-time migration of an `a2kit.scaffold` namespace into core, and names core files `runner.py` and `cli.py` that do not exist in the current core tree.

**Migration**: There is no `a2kit.scaffold` namespace. Composition primitives live in the current core modules; consult `module-layout-discipline`.

### Requirement: contrib namespace is deleted

**Reason**: This requirement polices a completed one-time deletion of an `a2kit.contrib` namespace. It is a migration artifact, not an ongoing contract.

**Migration**: There is no `a2kit.contrib` namespace.

### Requirement: ConnectionConfig adopts pydantic-settings (Contract B)

**Reason**: This requirement is owned by the connections capability (`core-composition` documents `ConnectionConfig` as a Pydantic-settings base; the connections package owns load-time substitution). It does not belong in `thin-core-surface` and duplicates the connections contract.

**Migration**: See the `core-composition` capability's "Connections package exposes plain classes and a CLI factory" requirement.

### Requirement: DI uses uncalled_for parameter-default form

**Reason**: a2kit does not use `uncalled_for` and has no `Depends` symbol. DI is constructor-injection plus the `provide`/`Container` surface (see `core-composition`, `request-scoped-di`). The entire `Depends`/`uncalled_for` model this requirement specifies was never the shipped design.

**Migration**: DI is the `app.provide(...)` registration surface and typed-kwarg injection. There is no `Depends`, no `uncalled_for`. See `request-scoped-di`.

### Requirement: A2K-DI lint rules catch misuse

**Reason**: This requirement mandates lint rules `A2K-DI-ANNOTATED`, `A2K-DI-IMPORT-LEGACY`, `A2K-DI-IMPORT-SLOW`, `A2K-DI-KWONLY` that police `Depends` / `uncalled_for` usage. None of those rules exist, and the `Depends` model they police does not exist.

**Migration**: There are no `A2K-DI-*` lint rules of this family. DI misuse surfaces at resolution time, not as static lint findings.

### Requirement: Single-entry `a2kit.run(app)` dispatches all modes

**Reason**: The `a2kit.run(app)` entry point is owned by current lifecycle/composition capabilities (`app-builder-runtime`, `core-composition`). This requirement's scenarios assert a `schema` command and a `serve` command shape that belong to the CLI capability, not to `thin-core-surface`.

**Migration**: See `app-builder-runtime` for the `a2kit.run` finisher and the CLI capabilities for command shape.

### Requirement: `build_mcp_server` forwards FastMCP kwargs

**Reason**: This is an MCP-package contract; it belongs to an MCP capability, not `thin-core-surface`. It is left out of this reconciliation rather than relocated (relocation is out of scope); if `build_mcp_server` kwarg-forwarding needs a spec, that is a follow-up.

**Migration**: `build_mcp_server` behavior is owned by the MCP package; consult its source.

### Requirement: ToolContext Protocol provides protocol-neutral logging + progress

**Reason**: The `ToolContext` re-export and CLI-stub behavior are owned by the `mcp-context-passthrough` capability, which specifies them in current terms. This requirement duplicates that contract and additionally asserts a `runtime.py` core file that does not exist.

**Migration**: See the `mcp-context-passthrough` capability for `a2kit.ToolContext` and the CLI/MCP context behavior.

### Requirement: Enrichers are protocol-neutral; both MCP and CLI honor them

**Reason**: This requirement mandates a `packages/enrichers/` package with a `wrap(fn, enricher)` helper. No `packages/enrichers/` directory exists. Enrichers are declared on routers via the `enrichers` class attribute / `enrich` method (see `router-conventions`).

**Migration**: See the `router-conventions` capability's "Routers declare enrichers via class attribute and/or `enrich` method" requirement. There is no `packages/enrichers/` package.

### Requirement: CLI tool output flows through the formatter

**Reason**: This requirement asserts a `--format=auto|tsv|toon|json` flag. TOON was retired as a wire format; the live formats are JSON, TSV, and page-tsv (see `type-driven-format-routing`). The CLI-output-through-formatter behavior is owned by the CLI / format-routing capabilities.

**Migration**: See `type-driven-format-routing` and the consumer-aware rendering capabilities. There is no `toon` format.

### Requirement: Schema discovery surface

**Reason**: This requirement asserts `--schema` flags and a top-level `schema` command rendered "TOON by default." TOON is retired, and schema-command behavior is a CLI-package concern, not a `thin-core-surface` one.

**Migration**: Schema-discovery behavior is owned by the CLI package; consult its source. There is no TOON rendering.

### Requirement: CLI adapter provides progressive disclosure by Router

**Reason**: This requirement asserts the CLI derives the Router subgroup slug from `Router.__name__`. The slug is an explicit class attribute, never derived (see `router-conventions`). Progressive-disclosure CLI shape is a CLI-package concern.

**Migration**: See `router-conventions` for the slug (explicit attribute). CLI progressive disclosure is owned by the CLI package.

### Requirement: Logging wrapper deleted

**Reason**: This requirement polices a completed one-time deletion of an `a2kit.logging` wrapper module. It is a migration artifact, not an ongoing contract.

**Migration**: There is no `a2kit.logging` wrapper. Logging is the LDD capability.

### Requirement: Testing wrappers reduced to thin fixtures

**Reason**: This requirement polices a completed one-time removal (`_cassette.py`, schema-snapshot wrappers). The current testing surface is owned by the `in-process-test-client` capability.

**Migration**: See the `in-process-test-client` capability for the current testing surface.

### Requirement: Test override pattern uses uncalled_for primitives

**Reason**: This requirement mandates `uncalled_for.resolved_dependencies` and forbids `app.dependency_overrides`. a2kit uses neither `uncalled_for` nor a `dependency_overrides` map. The test-override pattern is composition-root re-registration (`app.provide` last-write-wins).

**Migration**: See the `request-scoped-di` capability's "Re-registration is last-write-wins (test override pattern)" scenario.

### Requirement: `App.use_factory` binds Depends factories to a stable identity

**Reason**: `App.use_factory` does not exist. The method was never shipped; the `Depends`-factory-binding model it serves does not exist either.

**Migration**: There is no `App.use_factory`. Register factories with `app.provide(T, factory)`; see `request-scoped-di`.

### Requirement: CLI option synthesis maps nullable primitives to native Click types

**Reason**: This is a CLI-package implementation contract, not a `thin-core-surface` concern. It is left out of this reconciliation rather than relocated; if CLI option synthesis needs a spec, that is a follow-up.

**Migration**: CLI option synthesis is owned by the CLI package; consult its source.

### Requirement: Schema dump output respects character cap

**Reason**: This is a CLI-package implementation contract (truncation of `<app> schema` output), not a `thin-core-surface` concern.

**Migration**: Schema-output truncation is owned by the CLI package; consult its source.
