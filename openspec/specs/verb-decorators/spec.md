# verb-decorators Specification

## Purpose
TBD - created by archiving change de-magic-3. Update Purpose after archive.
## Requirements
### Requirement: `@a2kit.list_(...)` consolidates list-view settings

`@a2kit.list_(*default_fields: str, page_size: int | None = None, selectable_fields: tuple[str, ...] | None = None, name: str | None = None, reports: type | None = None, idempotent: bool = False, open_world: bool = False, title: str | None = None, surfaces: ... = UNSET)` SHALL accept the same semantic-flag and routing kwargs as the other verb decorators (`read`, `write`), in addition to its list-shape-specific kwargs (`*default_fields`, `page_size`, `selectable_fields`). Surface placement is governed solely by `surfaces=` (capability `surfaces-projection`); the legacy `visibility=` / `expose=` kwargs are NOT accepted.

`destructive=` SHALL NOT be accepted on `@a2kit.list_` (list is a read shape; matches the `@a2kit.read` contract — passing `destructive=True` raises `TypeError`).

#### Scenario: `title=` and `idempotent=` propagate to ToolAnnotations
- **WHEN** a tool is decorated `@a2kit.list_("id", title="Projects", idempotent=True)`
- **THEN** `meta.annotations.title == "Projects"`
- **AND** `meta.annotations.idempotentHint is True`
- **AND** `meta.annotations.readOnlyHint is True`

#### Scenario: `visibility=` is rejected as an unknown kwarg
- **WHEN** a tool is decorated `@a2kit.list_("id", visibility="cli")`
- **THEN** `TypeError` is raised naming `visibility` as an unexpected keyword argument
- **AND** no `meta.extras.visibility` field exists (use `surfaces=("cli",)`)

#### Scenario: `destructive=True` is rejected
- **WHEN** a tool is decorated `@a2kit.list_("id", destructive=True)`
- **THEN** `TypeError` is raised (list is read-shaped)

### Requirement: `selectable_fields` is derived from return-type annotation

When `selectable_fields` is omitted, the framework SHALL derive it from the tool's return annotation: a `list[T]` return where `T` is a Pydantic `BaseModel` or `dataclass` SHALL produce `tuple(T.__pydantic_fields__)` or the dataclass field names. When `selectable_fields` is provided explicitly, the explicit value SHALL be used unchanged.

#### Scenario: Derivation from list[Model]
- **GIVEN** a tool method `async def list_tasks(...) -> list[Task]` decorated `@a2kit.list_("id", "title")`
- **WHEN** the framework collects metadata
- **THEN** `meta.list_view.selectable_fields` equals the field names of `Task` in declaration order

#### Scenario: Explicit override
- **WHEN** the decorator is `@a2kit.list_("id", selectable_fields=("id", "title"))`
- **THEN** `selectable_fields` is `("id", "title")` even if `Task` has more fields

#### Scenario: Validation of default_fields ⊆ selectable_fields
- **WHEN** `@a2kit.list_("id", "missing")` is applied to a tool whose return type's fields do not include `"missing"`
- **THEN** lint rule reports a violation at collect time

### Requirement: Verb decorators accept MCP annotation kwargs

Verb decorators SHALL accept the semantic-flag kwargs (`open_world`, `title`; plus `idempotent`, `destructive` on write-verbs only — see "Verb decorators reject incompatible annotation kwargs") and the routing kwarg `reports`. Verb decorators SHALL NOT accept a `tags=` kwarg (framework-derived tags `"read"`, `"write"`, `"list"` are stamped automatically). Verb decorators SHALL NOT accept a `name=` kwarg on the public surface; the tool name SHALL be derived from `fn.__name__`. The internal `_meta.health` registration MAY use a private `_read_internal` helper that exposes `name=`; that helper is not part of the public API.

The same verb decorators SHALL apply to **App-level methods** as well as Router methods, and SHALL be auto-collected at class-definition time (the App is a class authored the same way as a Router — see `core-composition`). The auto-derive-from-`fn.__name__` rule is identical for both roots; only the canonical-name prefix differs:

- A **Router** verb resolves to `slug_leaf` (the router's `slug`, an underscore, then `fn.__name__`), e.g. `entity_update`.
- An **App-level** verb has **no slug**, so it resolves to the **bare `leaf`** (`fn.__name__`) with no app-name prefix. The app name is identity, never a prefix — there is no `kay_health`. An app-level verb therefore projects as a **top-level, bare-named command**: `health` on MCP, `app health` on the CLI, `/api/health` on HTTP.

(The full canonical-name resolution precedence and the `canonical_name_override` escape are defined by the co-shipping `native-tree-homomorphism` change; this requirement states only that app-level verbs are bare by that same rule.)

#### Scenario: `tags=` kwarg is rejected

- **WHEN** a tool is decorated `@a2kit.read(tags={"custom"})`
- **THEN** Python raises `TypeError` (unexpected keyword argument)

#### Scenario: `name=` kwarg is rejected on public surface

- **WHEN** a tool is decorated `@a2kit.read(name="custom-name")`
- **THEN** Python raises `TypeError` (unexpected keyword argument)
- **AND** the error message points the author at renaming the method

#### Scenario: Auto-derived name from method

- **WHEN** a Router method `async def list_tasks(...) -> list[Task]` is decorated `@a2kit.list_()`
- **THEN** the resulting tool name is `"list_tasks"` (or kebab-cased equivalent per the framework convention)

#### Scenario: Auto-stamped verb tags still appear

- **WHEN** a tool is decorated `@a2kit.read()`
- **THEN** `meta.tags == frozenset({"read"})`

#### Scenario: App-level verb produces a bare-named top-level command

- **GIVEN** `class Kay(a2kit.App): @a2kit.read def health(self) -> Health: ...`
- **WHEN** the App is composed and its surfaces are built
- **THEN** the verb's canonical name is the bare `"health"` (no app-name prefix — no `kay_health`)
- **AND** it renders `health` on MCP, `app health` on the CLI, and `/api/health` on HTTP

#### Scenario: App-level vs Router-level prefix differs by the same rule

- **GIVEN** an app-level `@a2kit.read def update(...)` and a Router `Entity(slug="entity")` with `@a2kit.read def update(...)`
- **WHEN** both are composed on the same App
- **THEN** the app-level verb resolves to bare `"update"` and the router verb resolves to `"entity_update"` — same `fn.__name__` rule, different prefix (none vs `slug_`)

### Requirement: Verb decorators reject incompatible annotation kwargs

`@a2kit.read` and `@a2kit.list_` SHALL raise `TypeError` at decoration time if `destructive=` or `idempotent=` is passed. Both flags are meaningful in the MCP spec only when `readOnlyHint=false` (i.e., on write-verbs). Reads are non-destructive and idempotent by definition. The TypeError SHALL name the rejected kwarg and the verb, and SHALL suggest `@a2kit.write` as the alternative if the author intended write-like semantics.

`@a2kit.write` SHALL continue to accept `destructive=` and `idempotent=`.

The bare `@a2kit.tool` decorator SHALL be removed; authors choose `@read` / `@write` / `@list_` based on the tool's semantics.

#### Scenario: destructive on read raises

- **WHEN** a tool is decorated `@a2kit.read(destructive=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb

#### Scenario: idempotent on read raises

- **WHEN** a tool is decorated `@a2kit.read(idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb
- **AND** the message explains that reads are spec-idempotent by definition
- **AND** the message suggests `@a2kit.write` if a repeat-safe write was intended

#### Scenario: idempotent on list raises

- **WHEN** a tool is decorated `@a2kit.list_("id", idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming the kwarg and the verb

#### Scenario: @a2kit.tool is removed

- **WHEN** consumer code references `a2kit.tool`
- **THEN** the import raises `AttributeError` with a message suggesting `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` as the replacements

#### Scenario: destructive on write still accepted

- **WHEN** a tool is decorated `@a2kit.write(destructive=False)`
- **THEN** no error is raised
- **AND** the `destructiveHint` annotation is set to `False`

#### Scenario: idempotent on write still accepted

- **WHEN** a tool is decorated `@a2kit.write(idempotent=True)`
- **THEN** no error is raised
- **AND** the `idempotentHint` annotation is set to `True`

### Requirement: Verb decorators reject mixing explicit annotations with flag kwargs

Verb decorators SHALL raise `TypeError` at decoration time when an explicit `annotations=ToolAnnotations(...)` argument is passed alongside any of the flag kwargs (`idempotent`, `open_world`, `destructive`, `title`). The two paths are mutually exclusive: either compose annotations via flag kwargs, or pass the explicit object. Silent winners are not permitted.

#### Scenario: annotations + flag kwarg raises

- **WHEN** a tool is decorated `@a2kit.write(annotations=ToolAnnotations(title="X"), idempotent=True)`
- **THEN** a `TypeError` is raised at decoration time naming both `annotations` and the conflicting flag kwarg(s)
- **AND** the message instructs the author to pick one path

#### Scenario: annotations alone still accepted

- **WHEN** a tool is decorated `@a2kit.write(annotations=ToolAnnotations(title="X", idempotentHint=True))`
- **THEN** no error is raised
- **AND** the resulting annotations match the explicit object exactly

#### Scenario: flag kwargs alone still accepted

- **WHEN** a tool is decorated `@a2kit.write(idempotent=True, title="X")`
- **THEN** no error is raised
- **AND** the resulting `ToolAnnotations` carries `idempotentHint=True` and `title="X"`

### Requirement: `@a2kit.list_` validates list-shaped return annotation at decoration

The `@a2kit.list_` decorator SHALL inspect the decorated function's return annotation at decoration time. If `typing.get_origin(return_annotation)` is not in `{list, tuple, set, frozenset}`, the decorator SHALL raise `TypeError` naming the function, the actual annotation, and the expected `list[T]` shape. A missing return annotation (`None` origin) SHALL also raise. Generic `list` (without a type parameter) SHALL be allowed but emits a one-time warning at decoration that selectable-field derivation will be empty.

#### Scenario: non-list return raises

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> dict: ...`
- **THEN** a `TypeError` is raised at decoration time naming `f`, the actual annotation `dict`, and the expected `list[T]` shape

#### Scenario: missing return annotation raises

- **WHEN** `@a2kit.list_("id")` decorates a function with no return annotation
- **THEN** a `TypeError` is raised at decoration time

#### Scenario: list[T] is accepted

- **WHEN** `@a2kit.list_("id")` decorates `async def f(...) -> list[Task]: ...`
- **THEN** no error is raised
- **AND** selectable fields are derived from `Task`

#### Scenario: tuple/set/frozenset returns are accepted

- **WHEN** `@a2kit.list_("id")` decorates a function returning `tuple[Task, ...]` (or `set[Task]` / `frozenset[Task]`)
- **THEN** no error is raised

### Requirement: `@a2kit.list_(page_size=...)` rejects non-positive values

The `@a2kit.list_` decorator SHALL raise `ValueError` at decoration time when `page_size` is passed as a value less than or equal to zero. `page_size=None` SHALL continue to mean "no pagination."

#### Scenario: zero page_size raises

- **WHEN** `@a2kit.list_("id", page_size=0)` is applied to a tool
- **THEN** a `ValueError` is raised at decoration time naming the offending value

#### Scenario: negative page_size raises

- **WHEN** `@a2kit.list_("id", page_size=-1)` is applied to a tool
- **THEN** a `ValueError` is raised at decoration time

#### Scenario: positive page_size accepted

- **WHEN** `@a2kit.list_("id", page_size=20)` is applied to a tool
- **THEN** no error is raised
- **AND** `meta.list_view.page_size == 20`

### Requirement: Semantic flags are a locked transport-neutral vocabulary

Four decorator kwargs SHALL form a locked transport-neutral semantic
vocabulary: `idempotent`, `open_world`, `destructive`, `title`. They
MUST NOT be treated as MCP-specific escape hatches. Each flag MUST
have a meaningful read on at least two transports. Any addition to
this vocabulary MUST be captured in an ADR superseding or extending
`docs/adr/0003-semantic-flag-vocabulary.md`.

#### Scenario: Vocabulary is documented in ADR 0003
- **WHEN** a contributor reads `docs/adr/0003-semantic-flag-vocabulary.md`
- **THEN** the ADR enumerates the four flags
- **AND** lists the per-transport read for each (MCP, CLI, REST, GraphQL)
- **AND** documents the contract for adding new flags (two-transport minimum)

#### Scenario: `annotations={...}` collapse is explicitly rejected
- **WHEN** a future audit proposes collapsing the four flags into one `annotations={...}` dict
- **THEN** ADR 0003 names this collapse as the rejected alternative and points at why (would promote MCP to a privileged transport in the surface)

### Requirement: `visibility` kwarg controls transport mounting tier

The `visibility` and `expose` kwargs SHALL NOT exist on the verb decorators. Surface placement and advertisement are governed solely by the `surfaces` kwarg (see capability `surfaces-projection`), which assigns each registered surface one of three states `ABSENT | LISTED | UNLISTED`. The former `visibility` tiers map onto the matrix as a migration recipe (recorded in the CHANGELOG):

- `visibility="hidden"` → `surfaces={<surface>: "unlisted"}` (`UNLISTED`: mounted + callable, absent from listing/help/schema).
- `visibility="cli"` → `surfaces=("cli",)` (`LISTED` on the CLI, `ABSENT` on every network surface).
- `visibility="all"` → omit `surfaces=` (default `LISTED` on every registered surface).

Passing `visibility=` or `expose=` to any verb decorator SHALL raise the language-default unexpected-keyword-argument `TypeError` (the kwargs are absent from the signature — caught statically by type checkers and at decoration time at runtime). No bespoke migration hint is embedded; the rewrite recipe lives in the CHANGELOG. A Router class attribute named `visibility` is likewise retired with **no** class-level surface default — surface placement is per-verb `surfaces=`, defaulting to `LISTED` on every surface when omitted.

#### Scenario: `visibility=` is rejected as an unknown kwarg
- **GIVEN** a verb decorator `@a2kit.write`
- **WHEN** a tool is decorated `@a2kit.write(visibility="cli")`
- **THEN** a `TypeError` is raised naming `visibility` as an unexpected keyword argument
- **AND** the decorator signature does not declare `visibility`

#### Scenario: `expose=` is rejected as an unknown kwarg
- **GIVEN** a verb decorator `@a2kit.read`
- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** a `TypeError` is raised naming `expose` as an unexpected keyword argument

#### Scenario: cli tier maps to single-surface tuple
- **GIVEN** a verb formerly authored `@a2kit.read(visibility="cli")`
- **WHEN** it is migrated to `@a2kit.read(surfaces=("cli",))`
- **THEN** the resolved state is `LISTED` on `cli`
- **AND** the verb is `ABSENT` on every network surface

#### Scenario: all tier is the default
- **GIVEN** a verb formerly authored `@a2kit.read(visibility="all")`
- **WHEN** it is migrated by omitting `surfaces=`
- **THEN** the resolved state is `LISTED` on every registered surface

### Requirement: Verb decorators accept `timeout=` kwarg

The verb decorators `@a2kit.read`, `@a2kit.write`, and `@a2kit.list_` SHALL accept a `timeout` keyword argument with the following forms:

- `timeout=None` (default) — no timeout; the tool body owns its own budget if any.
- `timeout=<number>` (float or int) — interpreted as seconds.
- `timeout=<string>` — bare number or with unit suffix `"ms"` (milliseconds), `"s"` (seconds), or `"m"` (minutes). Example: `"60s"`, `"2m"`, `"500ms"`.

The decorator SHALL parse the value at decoration time. Invalid string forms SHALL raise `TypeError` immediately, not at call time. The canonical normalized value (float seconds) SHALL be stored on `A2KitMetaExtras.timeout_seconds`.

When `timeout_seconds` is set, the dispatcher (both MCP and CLI transports) SHALL wrap the tool body in an `anyio.fail_after(seconds)` cancel scope. The scope SHALL sit innermost in the wrapper chain — inside the log-state scope and the dispatch-hook DI resolution — so neither DI cost nor log scope setup counts against the budget. On timeout, the wrapper SHALL raise Python's built-in `TimeoutError`.

The MCP transport's structured error envelope SHALL serialize `TimeoutError` as `{"class": "TimeoutError", "message": ...}` per the `mcp-structured-wire-error-envelope` contract. The CLI transport SHALL surface `TimeoutError` via the existing non-zero-exit + stderr-traceback path.

`A2KitMeta.annotations_as_dict()` SHALL surface `timeout_seconds` (when set) under the `a2kit` extras namespace, so MCP consumers reading `tool.meta` can plan retry policy.

#### Scenario: Float timeout is honored over MCP

- **GIVEN** `@a2kit.read(timeout=0.05)` on a tool whose body sleeps 0.5 seconds
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the response is `isError=True`
- **AND** `json.loads(content[0].text)["class"] == "TimeoutError"`

#### Scenario: String form `"60s"` parses to 60.0 seconds

- **GIVEN** `@a2kit.read(timeout="60s")` on a tool
- **WHEN** the tool's `A2KitMeta` is inspected
- **THEN** `meta.extras.timeout_seconds == 60.0`

#### Scenario: String form `"500ms"` parses to 0.5 seconds

- **GIVEN** `@a2kit.read(timeout="500ms")` on a tool
- **WHEN** the tool's `A2KitMeta` is inspected
- **THEN** `meta.extras.timeout_seconds == 0.5`

#### Scenario: Invalid timeout string raises at decoration time

- **WHEN** `@a2kit.read(timeout="2 hours")` decorates a tool
- **THEN** the decoration raises `TypeError`

#### Scenario: Timeout meta surfaces in annotations dict

- **GIVEN** `@a2kit.read(timeout=30.0)` on a tool
- **WHEN** the test inspects `meta.annotations_as_dict()`
- **THEN** the returned dict contains `{"a2kit": {..., "timeout_seconds": 30.0, ...}}`

#### Scenario: No timeout means no fail_after wrapper installed

- **GIVEN** `@a2kit.read()` (no `timeout=`) on a tool whose body sleeps 0.5 seconds
- **WHEN** the tool is invoked
- **THEN** the call completes successfully — no `TimeoutError`

### Requirement: `get_meta` and `set_meta` are not public

`a2kit.metadata` SHALL NOT expose `get_meta` or `set_meta` as callable accessors. Their underscored counterparts (`_get_meta`, `_set_meta`) are module-private and restricted to the composition-path allowlist `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}`.

The public-name shims SHALL raise `AttributeError` with a migration hint pointing at `AppRuntime.descriptor_for(name)` and `ToolDescriptor`. The shims SHALL not be removed entirely — they remain as a loud-failure surface so external code that previously imported them gets a clear error rather than a `NameError`.

#### Scenario: decorator stamps via private API

- **GIVEN** a verb decorator like `@a2kit.read(...)` is applied to a function
- **WHEN** the decorator stamps `A2KitMeta` on `fn.__a2kit__`
- **THEN** it uses `metadata._set_meta(fn, meta)` (private)
- **AND** no external module reads back via `get_meta` or `_get_meta`

#### Scenario: external import of get_meta fails loudly

- **GIVEN** a downstream package writes `from a2kit.metadata import get_meta`
- **WHEN** the package calls `get_meta(fn)`
- **THEN** `AttributeError` is raised with the migration hint

### Requirement: expose= validates against the live surface registry

The `expose=` kwarg SHALL be removed from the verb decorators
(`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`). Surface presence is
expressed by the `surfaces=` kwarg (see capability `surfaces-projection`):
a tuple of names resolves to `LISTED` on those names and `ABSENT`
elsewhere; a dict assigns explicit per-surface state.

The surface **names** used in `surfaces=` SHALL be validated against the
set of currently-registered surface names. The set MUST be obtained at
decoration time from a kernel-layer name registry that is kept in sync
with `SURFACE_REGISTRY` by a side-effect of `register_surface()`. The
literal `frozenset({"mcp", "api"})` MUST NOT appear in the verb-decorator
validation path. An unregistered name (whether in a tuple or as a dict
key) SHALL raise `TypeError` enumerating the registered names.

Passing `expose=` to any verb decorator SHALL raise `TypeError` at
decoration time, naming `surfaces=` as the replacement (e.g.
`expose=("mcp",)` → `surfaces=("mcp",)`).

#### Scenario: A registered surface name is accepted

- **GIVEN** the MCP and HTTP packages are imported (their surfaces self-register)
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("mcp",))`
- **THEN** the decorator does not raise

#### Scenario: An unregistered surface name is rejected with an enumerated message

- **GIVEN** the MCP and HTTP packages are imported
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("foo",))`
- **THEN** the decorator raises `TypeError`
- **AND** the error message enumerates the currently-registered surface names (e.g. "Registered surfaces: ('mcp', 'api')")
- **AND** the error message does not embed a hardcoded surface name list

#### Scenario: A newly-registered surface name is accepted without code changes to verbs

- **GIVEN** a test fixture registers a synthetic `StubSurface(name="test")`
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("test",))`
- **THEN** the decorator does not raise
- **AND** no edits to `src/a2kit/_verbs.py` were required

#### Scenario: Empty registry raises an actionable message

- **GIVEN** no Surface implementations have been imported
- **WHEN** a tool is decorated `@a2kit.read(surfaces=("mcp",))`
- **THEN** the decorator raises `TypeError`
- **AND** the message instructs the author to import a surface-mounting package (e.g. `a2kit.packages.mcp`)

#### Scenario: `expose=` is rejected with a migration hint

- **WHEN** a tool is decorated `@a2kit.read(expose=("mcp",))`
- **THEN** a `TypeError` is raised at decoration time
- **AND** the message names `surfaces=` as the replacement (`surfaces=("mcp",)`)

