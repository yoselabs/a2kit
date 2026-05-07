# Changelog

## 0.9.0 — 2026-05-07

**Ergonomic overhaul.** Pre-1.0, no users — clean breaks across error
handling, capability declarations, list-view tools, and the connection-key
contract. Most tool signatures get shorter; the agent-facing schema gets
sharper; the kit's mental model collapses by one layer.

### New

- **`@Router.read()` / `@Router.write()` auto-inject `connection: str`** into
  the agent-facing schema whenever the Router has a store. Authors stop
  writing `connection_param="conn"` and stop adding `conn: str` to their fn
  signature.

- **Type-driven info DI** — declare a `ConnectionInfo`-subclass typed
  parameter on your fn (`info: WidgetConn`); the kit binds the resolved info
  there at call time. Hidden from the agent-facing schema. `Router.context.info()`
  survives as the helper-function escape hatch:

  ```python
  @WidgetsRouter.read()                                  # zero kwargs
  async def list_widgets(info: WidgetConn) -> list[dict]:
      return [{"url": info.url}]
  # Agent calls list_widgets(connection="prod"); kit resolves + injects info.
  ```

- **List-view triad** — three orthogonal flags, two execution modes each:

  | Concern    | Local (kit handles)               | Passthrough (tool handles)              |
  |------------|-----------------------------------|------------------------------------------|
  | `filter`   | CEL post-process on rows          | thread `filter:str` to fn (compile to JQL/SQL/…) |
  | `fields`   | dict-key projection on rows       | thread `fields:list[str]` to fn          |
  | `pagination` | slice + opaque cursor encoding | thread `limit:int, cursor:str|None` to fn; tool returns `Page[T]` |

  Replaces v0.8's `projection=True` / `cel_filter_param=` / `fields_param=`
  with a coherent execution-mode story so MCPs that pushdown filtering or
  pagination upstream (a2db SQL, a2atlassian JQL) get first-class support
  alongside in-memory data sources (Reddit JSON, local lists).

- **`Page[T]`** — typed Pydantic generic for tools that own pagination
  upstream. `items: list[T]`, `next_cursor: str | None`. Kit unwraps and
  threads `next_cursor` into the outer `Response`.

- **Output formats split honestly: `tsv` vs `toon`** — flat rows render as
  TSV (header + tab-separated scalar cells); rows with at least one nested
  value render as TOON (same shape, but nested cells are compact-JSON-encoded
  inline). `Response.format` is now `Literal['tsv', 'toon', 'json']`. The
  v0.8 'toon' label was lying about the encoding.

- **`Router.capabilities` is `ClassVar`** — caps describe the router's *type*,
  not its runtime instance. Mirrors the existing `read_capabilities` /
  `write_capabilities` `ClassVar` pattern.

  ```python
  class IssuesRouter(a2kit.Router):
      capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}
  ```

- **Errors simplified — `EnricherFn = Callable[[Exception, str | None], Exception]`**
  replaces `ErrorEnricher` Protocol + `EnricherRegistry`. Composition via a
  6-line `chain(*fns)` helper. `connection_enricher(store)` factory replaces
  the `ConnectionNotFoundEnricher` class — closes over the store, returns a
  plain function.

  ```python
  @a2kit.tool(enricher=chain(my_enricher, connection_enricher(store)))
  async def query(...): ...
  ```

### Breaking

- `xml_guard` already renamed to `tool_call_guard` in v0.8 — this remains.
- **`projection=True`, `cel_filter_param=`, `fields_param=` removed.** Use
  `filter=Local|Passthrough`, `fields=Local|Passthrough`,
  `pagination=Local|Passthrough` instead.
- **`ErrorEnricher` Protocol, `EnricherRegistry`, `ConnectionNotFoundEnricher`
  class removed.** Use `EnricherFn` callables, `chain(*fns)`,
  `connection_enricher(store)` factory.
- **`ToolConfig` Pydantic model removed.** It was never wired to the live
  decorator — the authoritative kwarg contract is the `ToolKwargs` TypedDict.
- **`Router.capabilities` as a Pydantic instance field is gone.** Move to
  `ClassVar[set[Capability]]` on the subclass.
- **`Response.format` widened to `Literal['tsv', 'toon', 'json']`.** Existing
  `format == "toon"` assertions on flat data will return `"tsv"` instead.

### Soft-deprecated (drops in v0.10)

- **`connection_param=<name>` kwarg** still works as a back-compat alias for
  the v0.8 string-named connection lookup. New code should use the typed-info
  DI pattern (`info: <ConnectionInfo subclass>`).

### Internal

- 561 tests, 100% line+branch coverage, lint + ty clean.
- Examples still 5 files; example 03 renamed `03_projection_tool.py` → `03_list_view.py`
  and rewritten to demonstrate Local + Passthrough side-by-side.

## 0.8.0 — 2026-05-07

**Polish bundle.** Pre-1.0 cleanups surfaced after v0.7: rename
`xml_guard` → `tool_call_guard`, lift ephemeral handling out of the tool
decorator, type-tighten `Router.tool/.read/.write` signatures, type-promote
`format_response`, and add a `projection=True` ergonomic shortcut.

### New

- **`@a2kit.tool(projection=True)`** — auto-injects `filter: str` and
  `fields: list[str] | None` keyword-only params into the wrapper signature
  (FastMCP's tool schema picks them up; agents call with them) and post-processes
  the result through `format_response`. Authors no longer write any projection
  plumbing for the common case:

  ```python
  @a2kit.tool(projection=True)
  def list_widgets() -> list[dict]:
      """Return widgets."""
      return _WIDGETS
  ```

  Collisions with author-declared `filter`/`fields` params raise at decoration
  time. The explicit `cel_filter_param=`/`fields_param=` path remains as a
  power-user escape hatch and cannot combine with `projection=True`.

- **`a2kit.Response`** — typed Pydantic envelope returned by `format_response`.
  Fields: `format` (`Literal["toon", "json"]`), `data` (`str`), `truncated`
  (`bool`), `next_cursor` (`str | None`, reserved for v0.9 pagination). Frozen,
  `extra="forbid"`.

- **`Router.tool/.read/.write` signatures use `Unpack[ToolKwargs]`.** Authors
  composing higher-order Router classmethods now get end-to-end type-checking
  on the kwarg contract.

### Breaking

- **`xml_guard` → `tool_call_guard`** on `@a2kit.tool(...)`, `ToolConfig`, and
  the public `ToolKwargs` TypedDict. Same behaviour, less misleading name —
  the guard refuses any `str` arg containing `<parameter name=` (tool-call
  envelope contamination from agents), and that's a tool-call concern, not
  XML in the abstract.

- **`ToolXMLContamination` → `ToolCallContamination`.** Same shape, same
  message; renamed for symmetry with the kwarg.

- **`format_response` returns `Response`, not `dict`.** Migration: replace
  `env["format"]` with `env.format`, etc.

- **`ephemeral=` removed from public `@a2kit.tool` kwargs** and from the public
  `ToolKwargs` TypedDict. Ephemeral connections live at the Router level only —
  `Router(..., ephemeral={...})` works unchanged. Internally,
  `Router._apply_bindings` now wraps the effective store in a private
  `_EphemeralAwareStore` proxy so the tool decorator never thinks about
  ephemeral connections. Tools that previously passed `ephemeral=` directly to
  the decorator should construct an `_EphemeralAwareStore` explicitly or use a
  Router.

### Internal

- 556 tests, 100% line+branch coverage on 2224 statements / 832 branches.
  No changes to the linter pack, scaffold CLI, or runtime introspection seams.

## 0.7.0 — 2026-05-07

**Idiomatic Python pass.** Pre-1.0 cleanups: idiomatic `StrEnum Cap`, removal of
the `info` kwarg shape, auto-injected param docs, public `ToolKwargs`, FQN
ContextVar naming, A2K012 hardening, A2K013 added.

### New

- **`Cap` is a `StrEnum`.** `list(Cap)` enumerates all members; `Cap("write")`
  parses a raw string; `Cap.WRITE == "write"` is True; Pydantic v2 native
  serialization. The capability registry pre-registers built-ins via the same
  `capabilities.register(...)` path; lib code never branches on cap names.
- **Auto-inject param docs.** When a tool function has `connection_param="conn"`,
  the canonical `connection_param_doc(...)` text is prepended to the docstring
  at decoration time. Same for any `register_param_doc(name, text)` entry whose
  name matches a function parameter. Configurable via
  `[tool.a2kit.docs] auto_inject = false`.
- **A2K013** (advisory) — flags tool docstrings that still call
  `a2kit.docs.connection_param_doc(...)` / `param_doc(...)` via f-string;
  auto-injection covers it.
- **Public `ToolKwargs` TypedDict.** Use `Unpack[ToolKwargs]` for higher-order
  Router classmethod factories (e.g. a custom `expensive` decorator that
  defaults `Cap.EXPENSIVE`). New example: `examples/higher_order_decorator.py`.
- **A2K012 re-export resolution.** A2K012 now follows `from pkg import NAME`
  through `pkg/__init__.py` re-exports (cap depth 3) to confirm the constant
  terminates at a `Final[str]` annotation. Re-exports without a `Final[str]`
  terminus are flagged.

### Breaking

- **`info_kwarg` removed from `@a2kit.tool(...)`.** The kwarg-injection path
  (`*, info: ConnT | None = None`) is gone; the only supported access is
  `Router.context.info()`. `ToolConfig.info_kwarg` field also removed.
  Migration:

  ```python
  # Before:
  async def get_widget(conn: str, *, info: WidgetConn | None = None) -> dict:
      return {"url": info.base_url}

  # After:
  async def get_widget(conn: str) -> dict:
      info = WidgetsRouter.context.info()
      return {"url": info.base_url}
  ```

- **`Cap` is no longer a plain class with `Final[str]` constants.** Author
  syntax `Cap.WRITE`, `Cap.READ`, etc. is unchanged (StrEnum subclasses `str`,
  same equality semantics, same set/dict membership). The only observable
  difference: `Cap.WRITE.value == "write"` exposes the underlying string, and
  `repr(Cap.WRITE)` now shows `<Cap.WRITE: 'write'>`.

### Bug fixes

- **FQN-based `_RouterContext` ContextVar naming.** Two same-named Router
  classes in different modules (e.g. `app/jira/IssuesRouter` and
  `app/github/IssuesRouter`) used to share a ContextVar by `cls.__name__` and
  collide. v0.7 names the ContextVar with `f"{cls.__module__}.{cls.__qualname__}"`,
  giving each Router class independent state. Transparent rename — no author
  change needed.

### Examples

- **NEW** `examples/v07_minimal_mcp.py` (replaces `v06_minimal_mcp.py`) —
  StrEnum Cap demo + ContextVar-only flow.
- **NEW** `examples/higher_order_decorator.py` — `Unpack[ToolKwargs]` factory.
- **UPDATED** `examples/fat_tool.py`, `examples/router_class.py`,
  `examples/v03_minimal_mcp.py` — drop `info` kwarg, use ContextVar.

## 0.6.0 — 2026-05-07

**Router ergonomics + DI + type-verification + capability unification.** Additive
on top of v0.5.0; no destructive changes to v0.5 callers.

### New

- **Auto-derived Router names.** `class WidgetsRouter(a2kit.Router)` now slugs
  to `name="widgets"` automatically. `JiraConfluenceRouter` → `jira-confluence`.
  Explicit `name="..."` still wins.
- **`@MyRouter.read` / `.write` / `.tool` classmethod decorators.** Bind tools
  declaratively at module scope; `register_read` / `register_write` walk
  `cls._tools` by default. Each subclass gets its own fresh `_tools` list via
  `__init_subclass__` to avoid the mutable-default trap. Imperative override
  is still supported as the documented escape hatch (D).
- **Router-level DI.** Lift `store`, `enricher`, `resolver_registry`,
  `ephemeral` to the Router instance; every tool inherits. Per-tool decorator
  kwargs override.
- **`MyRouter.context.info()` typed accessor.** Each Router subclass gets a
  per-Router `_RouterContext` ClassVar backed by a `ContextVar`. The fat
  `@a2kit.tool` decorator sets it before the wrapped fn runs and resets after.
  The `*, info: ConnT` kwarg style still works in parallel and is opt-in
  (only injected if the function declares the kwarg or `**kwargs`).
- **Multi-store MCPs.** `Router(store=...)` per-router; `MCPRunner` aggregates
  via `RouterRegistry.routers_with_stores()`. CLI uses `--register router:key=...`
  namespaced parsing when >1 distinct store is registered; bare form raises
  with router-prefix suggestions.
- **A2K012 lint rule.** Advisory: raw-string custom capability that isn't a
  built-in `Cap.*` constant and isn't an imported / local `Final[str]` constant.
  Skipped on `tests/` and `examples/`.
- **Capability unification reframe.** Built-ins are pre-registered via the same
  `capabilities.register(...)` path as custom caps; `Cap` is a typed
  convenience reference (no special-casing in lib code). A2K009 stays as
  advisory for the built-in case.

### Breaking

- None for the v0.5 API surface. The `register_read` / `register_write`
  methods still exist; they now have a default implementation that walks
  `cls._tools`. Authors who override imperatively continue to work unchanged.

### Migration recipes

```python
# v0.5 — register_read with manual @a2kit.tool:
class WidgetsRouter(a2kit.Router):
    def register_read(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="conn")
        async def list_widgets(conn: str, *, info) -> list[dict]:
            return [{"url": info.url}]

# v0.6 — declarative + typed context:
class WidgetsRouter(a2kit.Router):
    pass

@WidgetsRouter.read(connection_param="conn")
async def list_widgets(conn: str) -> list[dict]:
    info = WidgetsRouter.context.info()  # typed
    return [{"url": info.url}]

routers.add(WidgetsRouter(store=store))
```

## 0.5.0 — 2026-05-07

**Breaking change.** `KEY_FIELDS: ClassVar[tuple[str, ...]]` is removed in favour
of a NamedTuple-based `Key` class declared via `key=` on the subclass. This
unlocks per-field types (e.g. `env: Literal["dev", "staging", "prod"]`),
keeps NamedTuple-as-tuple compatibility for the existing positional/tuple/kwargs
load shapes, and adds a fully-typed `store.load(WidgetKey(...))` shape.

**Migration recipe:**

```python
# Before (v0.4):
class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")

# After (v0.5):
from typing import NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str

class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    ...
```

Subclasses that still declare `KEY_FIELDS` raise `MigrationRequired` at class
creation time with a generated migration snippet. (Pre-1.0 clean cut: no alias,
no warning grace period.)

**New**

- `ConnectionInfo.__init_subclass__` accepts `key=<NamedTupleClass>`. The class
  is bound as `cls.Key`. Default is the built-in `_DefaultKey(name: str)`.
- `ConnectionStore.load()` accepts a NamedTuple instance directly as a
  fifth call shape: `store.load(WidgetKey(project="a", env="dev", db="c"))`.
  All previous shapes (kwargs / tuple / list / positional / bare-string) still work.
- `ConnectionStore.key_class` property — exposes `model.Key`.
- `ConnectionStore.list_keys()` — returns typed NamedTuple instances rather
  than raw `tuple[str, ...]`. Existing index-style access still works.
- New exception: `MigrationRequired`.
- Examples: `examples/typed_key_literal.py` (per-field `Literal` typing),
  renamed `examples/key_namedtuple.py` (was `key_fields.py`),
  renamed `examples/v05_minimal_mcp.py` (was `v04_minimal_mcp.py`).

**Behavioural changes**

- `KeyFieldMissing` / `KeyArityMismatch` messages now reference the NamedTuple
  class name (e.g. `"Missing key field 'env' on WidgetKey"`).
- A2K005 lint rule simplified: no longer validates `KEY_FIELDS` shape (the
  attribute is gone). Now flags any leftover `KEY_FIELDS = ...` as a v0.5
  migration error and continues to cross-check `connection_param` arity against
  `cls.Key._fields`.

**Removed**

- `KEY_FIELDS: ClassVar[tuple[str, ...]]` — gone. The `__init_subclass__`
  validator that warned on uppercase entries is also gone (NamedTuples enforce
  identifier-shape at the language level).

## 0.4.1 — 2026-05-07

Patch on top of v0.4.0. Three changes: `ty` becomes a hard gate, internal
client-name references are scrubbed from the working tree (and from prior
commits via history rewrite), and two example files are renamed to describe
their shape rather than their inspiring upstream MCP.

**Strict typing**

- `ty` is now a mandatory typecheck step. `make typecheck` no longer skips
  when ty isn't installed — `ty>=0.0.34` is a dev dependency. CI runs
  `uv run ty check src/` between ruff and pytest as a hard gate.
- Pre-commit hook for `ty` runs at `pre-push` (not `pre-commit`) since
  type-checking is comparatively slow.
- Migration: `uv sync --all-extras` if you were previously skipping ty.

**Privacy / generality**

- Connection-name examples no longer reference internal client names.
- Two example files renamed:
  - `examples/a2atlassian_style.py` → `examples/flat_key_style.py`
  - `examples/a2db_style.py` → `examples/multi_field_key_style.py`
- Prose references to `a2atlassian` / `a2db` in source comments, docstrings,
  README, ANTIPATTERNS, and CHANGELOG replaced with descriptive phrases
  ("a Jira/Confluence-wrapping MCP", "a SQL-wrapping MCP"). Real package
  imports (`atlassian-python-api`, `mcp.server.fastmcp`) are unchanged.

**History rewrite**

- v0.4.1 also rewrites the prior 4 commits via `git filter-repo` to scrub
  internal client connection-name references from commit history. Anyone with
  a clone before this point should
  `git fetch --all && git reset --hard origin/main` to sync. (Realistically:
  nobody has a clone — the repo was just published.)

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

Initial spike. `ConnectionStore` extracted from two upstream MCPs (a SQL
wrapper and a Jira/Confluence wrapper); pluggable `ResolverRegistry`; typed
exceptions on resolver failure.
