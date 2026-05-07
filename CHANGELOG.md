# Changelog

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
