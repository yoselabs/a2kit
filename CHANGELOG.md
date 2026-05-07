# Changelog

## 0.4.0 — 2026-05-07

Pre-1.0 clean cut. Removes all v0.3 deprecation aliases (no external consumers
to break). Adds CEL projection, completes A2K005, activates A2K010, ships
A2K011, auto-loads pyproject defaults, splits `_select.py`. Internal repo only —
not published to PyPI.

**Breaking changes (deprecation aliases removed):**

- `a2kit.Feature` / `a2kit.FeatureRegistry` — gone. `from a2kit import Feature`
  raises `ImportError` with a migration hint. Use `Router` / `RouterRegistry`
  (kwarg-init).
- `RouterRegistry.feature(...)` decorator — gone. Use `RouterRegistry.router(...)`.
- `MCPRunner` flags `--enable`, `--no-enable`, `--writes` — gone. The synthetic
  `(read or write)` clause translation is removed. Migration:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
- `build_cli(connection_class=...)` kwarg — gone. Derived from
  `store.connection_class`.
- `MCPRunner(connection_class=...)` kwarg — gone. Same derivation.
- `register_ephemeral_connections(args, connection_class)` positional — gone.
  Only `register_ephemeral_connections(args, store=store)` remains.

**New**

- `a2kit.projection` module: `filter_records(records, *, expr)` (CEL boolean
  expression filter), `project_fields(records, *, fields)` (key selection).
  `[projection]` extra brings in `cel-python>=0.5`. Lazy-imported; missing
  dep raises `ProjectionUnavailable`.
- `a2kit.format_response(data, *, filter="", fields=None, ...)` composes
  filter → projection → truncation → format routing.
- `@a2kit.tool(cel_filter_param="filter", fields_param="fields")` auto-threads
  the named function args into `format_response`.
- New exceptions: `ProjectionUnavailable`, `InvalidFilterExpression`.
- `MCPRunner` auto-loads `[tool.a2kit.runner] default_select` from the nearest
  `pyproject.toml` (walks up from CWD). Resolution order: explicit kwarg →
  pyproject value → hard default `"default and not write and not destructive"`.
- `[tool.a2kit.capabilities]` table in `pyproject.toml`. Each entry is
  registered into `a2kit.capabilities` at `MCPRunner.__init__` time. Same
  `CapabilityRecord` validation as the code-side path.
- **A2K010** lint activated: scans `default_select=...`, `parse_select(...)`,
  `--select "<expr>"` literals in source, `scripts/*.sh`, `Makefile`, and
  `pyproject.toml`. Unknown atoms emit `A2K010` with `difflib` suggestions.
- **A2K011** advisory lint: `@a2kit.tool` returning raw `dict`/`Mapping` is
  flagged ("prefer Pydantic BaseModel for richer schema snapshots").
  Configurable via `[tool.a2kit.lint] disabled = ["A2K011"]`. Suppressible
  via `# noqa: A2K011` on the function definition line.
- **A2K005 completed**: cross-checks tool `connection_param` type annotation
  against the resolved store's `KEY_FIELDS` arity. `str` for arity > 1 is
  rejected; `tuple[...]`, typed key model, or `dict[str, str]` accepted.
  Falls back to advisory when the store can't be resolved within the file.

**Cleanups / refactors**

- `_select.py` split into `_select_parse.py` (~110 LOC) + `_select_eval.py`
  (~40 LOC) + `_select.py` façade. Public re-exports unchanged.
- `examples/projection.py`, `examples/cel_filter_tool.py`,
  `examples/toml_capabilities.py`, `examples/v04_minimal_mcp.py` — new.
- ANTIPATTERNS.md adds entries 14–18 (Pydantic class-attr fields, runtime
  `Capability` alias, forward refs + `__future__` annotations, opt-in pytest
  plugins, hard breaks vs synthetic deprecation clauses).
- `tests/test_v04.py` covers projection, A2K005 multi-field, A2K010, A2K011,
  TOML capability loading, removal guards.

**No PyPI publish.** Repo push is the only release channel for v0.4.

## 0.3.1 — 2026-05-07

Patch on top of v0.3.0. Adds Router (Pydantic) + capabilities + select grammar
+ Pydantic configs + strict types. Backward-compatible aliases for one cycle.

**New**

- `Router` (Pydantic `BaseModel`, generic over `ConnT`) replaces `Feature`.
  Subclass and instantiate via kwargs: `IssuesRouter(name="issues", capabilities={Cap.EXTERNAL})`.
- `RouterRegistry.apply()` sets a thread-local `_active_router`; the fat
  `@a2kit.tool` decorator reads this via the **auto-tag seam** and merges
  the router's name + capabilities + `Cap.READ`/`Cap.WRITE` (per phase) onto
  every registered tool's tag set.
- `Cap` constants (`Cap.READ`, `Cap.WRITE`, `Cap.DESTRUCTIVE`, `Cap.EXPENSIVE`,
  `Cap.PII`, `Cap.EXTERNAL`).
- `a2kit.capabilities` namespace — register custom caps:
  `a2kit.capabilities.register("tickets-management", description="...")`.
- `--select` boolean expression flag on `MCPRunner`. Grammar:
  atoms (router/tool/capability names), operators `and`/`or`/`not`,
  optional `tool:` / `router:` / `cap:` namespace prefix, parentheses.
  Default: `default and not write and not destructive`.
- `a2kit.sel(...)` typed builder mirrors the CLI grammar via `&`, `|`, `~`.
- `SelectExpr` (Pydantic AST), `SelectAtom`, `parse_select()`.
- Pydantic configs: `ToolConfig`, `RunnerConfig`, `BudgetConfig` (all
  `extra="forbid"`, `frozen=True`).
- `ConnectionInfo.__init_subclass__` validates `KEY_FIELDS` shape (tuple,
  non-empty, identifier per entry, lowercase warned).
- `ConnectionStore.load(...)` unwraps `pydantic.ValidationError` and re-raises
  the underlying `KeyArityMismatch` / `KeyFieldMissing` / `InvalidConnectionKey`.
- `UnknownCapability` exception with `difflib`-based `suggestions=[...]`.
- New lint rules:
  - **A2K008** — Name collision across router/tool/capability namespaces.
  - **A2K009** — Raw built-in capability string (`'write'` instead of `Cap.WRITE`).
  - **A2K010** — Reserved (v0.4) — unknown atom in `--select` expressions.
- Ruff `ANN` rules added to `[tool.ruff.lint]` selection. `tests/` and
  `examples/` paths get per-file ignores for `ANN001`/`ANN201`/etc.
- New examples: `examples/router_class.py`, `examples/select_grammar.py`,
  `examples/typed_decorator.py`. Updated `examples/v03_minimal_mcp.py`,
  `examples/feature_class.py`.
- `make typecheck-strict` target (graceful fallback if ty unavailable).
- `.pre-commit-config.yaml`, `package.json` (jscpd + actionlint),
  `.jscpd.json`, `scripts/find_similar.py` (similar-tool-name detector).

**Breaking changes**

- `--enable` / `--no-enable` / `--writes` flags on `MCPRunner` are deprecated.
  They still work for one cycle (with `DeprecationWarning`) and are translated
  internally to a `--select` expression.

  Migration recipe:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
  - `--enable issues --writes` → `--select "router:issues and (read or write)"`

**Deprecations (one-cycle warning, removal in v0.4)**

- `Feature` / `FeatureRegistry` (use `Router` / `RouterRegistry`).
  Class-attribute style (`class IssuesFeature(Feature): name = "issues"`) is
  not supported under Pydantic; use `IssuesRouter(name="issues", ...)` instead.
- `RouterRegistry.feature(...)` decorator (use `RouterRegistry.router(...)`).
- `--enable` / `--no-enable` / `--writes` (use `--select`).

**Internal renames (underscore-prefixed; no external impact)**

- `a2kit/_capabilities.py`, `a2kit/_select.py`, `a2kit/_router_state.py`,
  `a2kit/_configs.py` — all leading-underscore internals.

## 0.3.0 — 2026-05-07

Feature class, KEY_FIELDS, server-auto-register, lint subpackage. Internal-only
release one day after v0.2 — applies a clean cut where it makes sense.

**Breaking changes**

- `KEY_PARTS: ClassVar[int | None]` → `KEY_FIELDS: ClassVar[tuple[str, ...]]`.
  No alias — pre-1.0 clean cut. Migration: replace `KEY_PARTS = N` with the
  field-named tuple, e.g. `KEY_FIELDS = ("project", "env", "db")`. Default
  `("name",)` covers the single-key case, so subclasses with `KEY_PARTS = 1`
  can simply drop the line.
- `build_cli(connection_class=...)` and `MCPRunner(connection_class=...)` are
  deprecated. The store knows its model — use `build_cli(store, name="...")`
  and `MCPRunner(server, store=store)`. Passing `connection_class=` still
  works for one cycle, with a `DeprecationWarning`.
- `register_ephemeral_connections(args, connection_class)` → prefer
  `register_ephemeral_connections(args, store=store)`. Old shape works with a
  warning.

**New**

- `@a2kit.tool(server=server, ...)` auto-registers the wrapped function with
  FastMCP's tool manager. Idempotent when stacked under an explicit
  `@server.tool()` (innermost) — the decorator detects an existing entry by
  name and skips. The single-decorator path is the new default; stacked form
  remains for callers who need explicit FastMCP options.
- `ConnectionInfo.KEY_FIELDS` — named-tuple key shape. Default `("name",)`.
  `ConnectionStore.load(...)` now accepts kwargs (`load(project=..., env=..., db=...)`),
  tuples, lists, positional args, and bare-string sugar for the single-field
  default.
- New typed exceptions: `KeyFieldMissing`, `KeyArityMismatch`.
- `ConnectionStore.connection_class` — exposes the bound model class.
- `a2kit.scaffold.Feature` — base class bundling enricher + snapshot_dir +
  cassette_dir + register hooks. The v0.2 `@registry.feature(name, ...)`
  decorator path is unchanged. Register an instance via `registry.add(MyFeature())`.
- `a2kit.docs.register_param_doc(name, text)` + `a2kit.docs.param_doc(name)`.
  Registered text is auto-injected into a tool's docstring when the existing
  docstring doesn't mention the parameter. Explicit text wins.
- `a2kit.lint` subpackage:
  - **Static rules:** `A2K001` (tool decorator missing param), `A2K002`
    (`-> str` returns), `A2K003` (module-local Pydantic return), `A2K004`
    (canonical connection-param helper), `A2K005` (`KEY_FIELDS` shape +
    usage), `A2K006` (duplicate param description).
  - **Runtime checks:** `A2KR001` (snapshot presence), `A2KR002` (per-tool
    budget), `A2KR003` (total schema budget), `A2KR004` (similar tool names).
  - CLI: `uvx a2kit lint paths...` and `uvx a2kit check --import path:server`.
  - Configurable via `[tool.a2kit.lint]` / `[tool.a2kit.check]`. Per-line
    `# noqa: A2KXXX`.
  - See `LINT.md` for rationale and examples.

**Examples added**

- `examples/v03_minimal_mcp.py` — < 30 LOC for a 2-tool MCP using `@a2kit.tool(server=...)`.
- `examples/feature_class.py` — `Feature` base class with enricher + snapshot dir.
- `examples/key_fields.py` — all four `load()` call shapes against a 3-part key.

Existing examples (`runner.py`, `scaffold_cli.py`, `feature_modules.py`) updated
to drop the now-redundant `connection_class=` kwarg.

**Deprecations (one-cycle warning, removal in v0.4)**

- `build_cli(connection_class=...)`
- `MCPRunner(connection_class=...)`
- `register_ephemeral_connections(args, connection_class)` (positional)

## 0.2.0 — 2026-05-07

Production-grade primitive set. Promotes a2kit from "ready for first external
consumer" to a foundation that absorbs every recurring MCP boilerplate at n=2.
All v0.1 API still imports unchanged; the bare `@a2kit.tool()` is byte-equivalent
to `@a2kit.tools.tool()` from v0.1.

**New modules:**

- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`. Vendored
  TOON encoder (~12 LOC) + recursive truncation + canonical envelope.
- `a2kit.docs` — `connection_param_doc(name, *, cli, example, custom_suffix)`.
  One canonical paraphrase for the connection-param docstring (eliminates
  per-tool phrasing drift).
- `a2kit._cassette` (re-exported as `a2kit.testing.cassette`) — vcrpy thin
  wrapper. Decorator + sync/async context manager.

**New scaffold primitives:**

- `a2kit.scaffold.MCPRunner` — wraps `server.run()` with `--register`,
  `--scope`, `--enable`, `--no-enable`, `--writes`, `--http [host:port]` parsing.
  Sets the thread-local transport seam used by `streaming=True` tools.
  Skippable: calling `server.run()` directly is fully supported.
- `a2kit.scaffold.FeatureRegistry` — decorator-style feature-module
  registration with `default=` flag and `apply(server, store, *, enabled,
  include_writes)`.

**Fat `@a2kit.tool` decorator** (extends v0.1 — every new arg is optional):

- `store=` + `connection_param=` + `info_kwarg=` — connection lookup +
  injection.
- `ephemeral=` — in-memory connections take priority over store.
- `resolver_registry=` — recursive `${ENV}` / `op://` resolution on every
  string field of the loaded `ConnectionInfo`.
- `write=True` — enforces `read_only` check; raises `WriteNotAllowed`.
- `xml_guard=True` (default) — refuses any `str` arg containing
  `<parameter name=`; raises `ToolXMLContamination`.
- `otel=True` (default) — wraps the call in `a2kit.tool.<name>` span when a
  non-default tracer provider is configured; no-op otherwise. Lazy import,
  optional `[otel]` extra.
- `streaming=True` — async-iterator returns collected on stdio, passed
  through on HTTP.
- `tool_name=` — explicit name for the OTel span (defaults to `__name__`).
- Public top-level alias `a2kit.tool` (v0.1 `a2kit.tools.tool` retained).
- Standalone helper `a2kit.tools.assert_clean_string(value, param_name)`.

**Pytest plugin additions:**

- `--update-cassettes` flag.
- `update_cassettes` boolean fixture.

**New exceptions:** `WriteNotAllowed`, `ToolXMLContamination`.

**Optional extras:**

- `[otel]` — `opentelemetry-api>=1.20`. Lazy-imported.
- `[testing]` — `vcrpy>=6`. Lazy-imported via `a2kit.testing.cassette`.

**Examples added:** `fat_tool.py`, `runner.py`, `formatter.py`,
`feature_modules.py`, `streaming_tool.py`, `cassette_test.py`. `scaffold_cli.py`
updated to use `MCPRunner`. `make examples` runs all of them end-to-end.

**Anti-patterns consolidated:** `ANTIPATTERNS.md` at repo root — 13 entries,
each with citation.

**No deprecations.** `a2kit.tools.tool` still exported.

## 0.1.0 — 2026-05-07

Initial thin-library release. Promotes a2kit from single-primitive spike to a v0.1
library ready for first external consumer.

**Public API surface:**

- `ConnectionInfo`, `ConnectionStore`, `default_config_dir` — TOML-backed
  named-connection store. Already in 0.0.1.
- `resolve_token`, `ResolverRegistry`, `resolve_env`, `resolve_op`, `resolve_literal`,
  `default_registry` — token resolvers (`${ENV_VAR}`, `op://...`, literal). Already
  in 0.0.1.
- `tools.tool` decorator — composes with FastMCP's `@server.tool()`. Refuses
  `-> str` returns at decoration time (`InvalidToolReturnTypeError`); rewrites
  return annotations on both wrapper and wrapped function. Optional `enricher`
  routes exceptions through an `ErrorEnricher`.
- `tools.preserve_return_annotation` — public utility for the annotation-rewrite
  trick alone, without the rest of `tool(...)`.
- `errors.ErrorEnricher` Protocol — `enrich(exc, *, tool_name) -> Exception`.
- `errors.EnricherRegistry` — chains enrichers in registration order; first
  divergent return wins.
- `errors.ConnectionNotFoundEnricher` — built-in enricher; adds
  `available_connections` and a `difflib` suggestion to `ConnectionNotFound`
  exceptions.
- `scaffold.build_cli(store, connection_class, name)` — Click group with
  `login`/`logout`/`connections list`/`connections show`/`connections delete`.
  Author adds their own commands via `cli.add_command(...)`.
- `scaffold.register_ephemeral_connections(args, connection_class)` — parses
  `--register KEY field=val ...` blocks from argv into in-memory connections.
- `scaffold.scope_filter(store, scope)` — read-only filtered store view.
- `testing.snapshot_schemas(server, dir)` — writes one compact-JSON file per
  FastMCP tool (file size = byte-accurate token-budget proxy).
- `testing.assert_schemas_match(server, dir)` — raises `SchemaSnapshotMismatch`
  on drift; message contains a unified diff.
- `pytest_plugin` — opt-in via `pytest_plugins = ["a2kit.pytest_plugin"]` in
  the consumer's `conftest.py`. Provides `schema_snapshot` fixture and
  `--update-schema-snapshots` flag.
- New exceptions: `InvalidToolReturnTypeError`, `SchemaSnapshotMismatch`.

**No deprecations.** All 0.0.1 API still imports unchanged.

**Out of scope (deferred):**

- Retry/rate-limit base client (anticipated at n=1; confirm or kill at n=3).
- Feature-module registration with `--enable` (anticipated at n=1).
- Pagination unification (anticipated at n=1).
- Output-format router (TSV/TOON/JSON) — module-level concern, not a primitive.
- Token-budget defaults — module-level concern.
- OTel integration — deferred to v0.2.

## 0.0.1 — 2026-05-07

Initial spike. `ConnectionStore` extracted from a2db + a2atlassian; pluggable
`ResolverRegistry`; typed exceptions on resolver failure.
