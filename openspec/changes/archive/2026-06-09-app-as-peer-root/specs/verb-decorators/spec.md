## MODIFIED Requirements

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
