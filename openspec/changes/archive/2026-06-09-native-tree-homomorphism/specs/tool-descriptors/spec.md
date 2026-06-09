## MODIFIED Requirements

### Requirement: `ToolDescriptor` carries projected tool shape

`ToolDescriptor` SHALL expose, in addition to `{name, router, fn, return_type, format_hint, encoding_plan, verb, expose, authorize}`, the following projected fields:

- `ctx_param_name: str | None` — name of the `ToolContext`-typed parameter on the tool function, or `None` if absent.
- `timeout: float | None` — per-tool timeout in seconds, projected from `A2KitMeta.extras.timeout_seconds`.
- `annotations_view: Mapping[str, Any]` — immutable view of `A2KitMeta.annotations_as_dict()` (no `mcp.types` import side effect on read).
- `metadata_view: Mapping[str, Any]` — immutable flattened view of `A2KitMeta` (verb, tags, context_param_name, extras as dict).
- `lazy_param_names: frozenset[str] | None` — parameter names whose annotation is `Lazy[T]`. `None` until descriptor materialization is moved to `runtime.build(app)`.
- `wire_param_names: frozenset[str] | None` — parameter names NOT resolved by the container and not `Lazy[T]` and not the ctx parameter. `None` until descriptor materialization is moved to `runtime.build(app)`.
- `router_slug: str | None` — the owning router's `slug`, or `None` for an app-level verb. Carried so every surface can render the canonical name without re-deriving the slug.
- `canonical_name_override: str | None` — the verbatim name pinned on the verb decorator (`canonical_name_override="…"`), or `None` when the name auto-derives. A non-`None` value MUST match `[A-Za-z0-9_]`.

All projected fields SHALL be immutable. `Mapping` views SHALL use `types.MappingProxyType` (or equivalent) so consumers cannot mutate the underlying dict.

`ToolDescriptor.name` SHALL be the **canonical name** produced by the one shared resolver `resolve_canonical_name(descriptor)`, applying this precedence (ADR 0028 decision 5):

```
canonical_name(descriptor) =
   1. canonical_name_override is not None  →  canonical_name_override   (VERBATIM, no slug prefix)
   2. else router_slug is not None         →  f"{router_slug}_{leaf}"   (leaf = fn.__name__)
   3. else                                 →  leaf
```

A pinned `canonical_name_override` is **complete** — the slug is NEVER re-applied (an override `"jira_search"` under `slug="jira"` resolves to `jira_search`, never `jira_jira_search`). Because tool names carry no prefix today (the current `name` is `fn.__name__` with no slug), every current explicit name already equals its post-change value; only auto-derived router verbs (step 2) change. `resolve_canonical_name` SHALL be a standalone pure function (no surface coupling) so it is the single resolver every surface renders through and the single function global-uniqueness enforcement (the dup-name lint rule and the Wave 3 runtime backstop) runs over.

#### Scenario: Descriptor exposes ctx_param_name

- **GIVEN** a tool `async def fetch(self, *, ctx: ToolContext, id: str) -> Memory: ...` registered on a router
- **WHEN** `app.tools()[0]` is read
- **THEN** the descriptor's `ctx_param_name == "ctx"`

#### Scenario: Descriptor exposes timeout

- **GIVEN** a tool decorated with `@a2kit.read(timeout=5.0)`
- **WHEN** the descriptor is materialized
- **THEN** `descriptor.timeout == 5.0`

#### Scenario: annotations_view is immutable and dict-shaped

- **GIVEN** a tool decorated with `@a2kit.read(annotations=ToolAnnotations(readOnlyHint=True))`
- **WHEN** `descriptor.annotations_view` is read
- **THEN** `descriptor.annotations_view["readOnlyHint"] is True`
- **AND** attempting `descriptor.annotations_view["readOnlyHint"] = False` raises `TypeError`

#### Scenario: metadata_view exposes verb

- **GIVEN** any `@a2kit.list_(...)`-decorated tool
- **WHEN** `descriptor.metadata_view["verb"]` is read
- **THEN** the value is `"list"`

#### Scenario: container-dependent fields default to None

- **GIVEN** the current descriptor materialization runs at `add_router` (pre-`runtime.build(app)`)
- **WHEN** `descriptor.wire_param_names` and `descriptor.lazy_param_names` are read
- **THEN** both return `None` until the deferral change lands

#### Scenario: Auto-derived router verb resolves to slug_leaf

- **GIVEN** a verb `update` on `Entity(slug="entity")` with no `canonical_name_override`
- **WHEN** `resolve_canonical_name(descriptor)` runs
- **THEN** the result is `"entity_update"` (`router_slug` + `"_"` + `fn.__name__`)
- **AND** `descriptor.name == "entity_update"`

#### Scenario: App-level verb resolves to bare leaf

- **GIVEN** an app-level verb `health` with `router_slug is None` and no override
- **WHEN** `resolve_canonical_name(descriptor)` runs
- **THEN** the result is `"health"` (no app-name prefix)

#### Scenario: canonical_name_override is verbatim, slug never re-applied

- **GIVEN** a verb under `slug="jira"` with `canonical_name_override="jira_search"`
- **WHEN** `resolve_canonical_name(descriptor)` runs
- **THEN** the result is `"jira_search"` exactly — NOT `"jira_jira_search"`

#### Scenario: Illegal override character rejected

- **GIVEN** a verb decorated `@a2kit.read(canonical_name_override="jira-search")`
- **WHEN** the decorator is applied
- **THEN** a `TypeError` is raised naming the offending value and the `[A-Za-z0-9_]` constraint
