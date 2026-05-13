# verb-decorators — explicit-router-surface delta

## ADDED Requirements

### Requirement: Verb decorators accept `reports=` and `enrichers=` kwargs

The verb decorators `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, and `@a2kit.tool` SHALL accept the following kwargs and write their values directly
into `A2KitMeta.extra` (or the typed extras shape introduced by
`align-with-pydantic-and-stdlib`) at decoration time:

- `reports: type | None = None` — declares the report type a tool
  produces. When non-`None`, stamped as `a2kit.report_type`.
- `enrichers: tuple[Callable[[Exception], str | None], ...] = ()` —
  per-tool exception enrichers, overriding the Router-level
  `enrichers` class attribute for this tool. When non-empty,
  stamped as `a2kit.tool_enrichers`.

The previous staging-decorator path (a sibling decorator stashing
`fn._a2kit_pending_extra` for the verb decorator to flush) SHALL be
removed. There SHALL be no side-channel attribute on the wrapped
function; the verb decorator is the single source of truth for
per-tool extras.

#### Scenario: reports kwarg stamps report type

- **WHEN** a tool is decorated `@a2kit.read(reports=Task)`
- **THEN** `A2KitMeta.extra["a2kit.report_type"]` equals `Task`

#### Scenario: enrichers kwarg overrides router-level enrichers

- **GIVEN** a router with class attribute `enrichers = (router_fb,)`
  and a tool decorated `@a2kit.read(enrichers=(tool_specific,))`
- **WHEN** the tool raises an exception
- **THEN** `tool_specific(exc)` runs first; if it returns `None`,
  `router_fb(exc)` runs second (per-tool wins, then router-level
  list, then router `enrich` method per `router-conventions`)

#### Scenario: Stacking decorators removed

- **WHEN** lint scans the repo
- **THEN** the `@reports(...)` standalone decorator and its hosting
  module are absent; any surviving import raises `ImportError`

#### Scenario: No pending-extra side channel

- **GIVEN** any function `fn`
- **WHEN** `fn` is decorated with any verb decorator
- **THEN** `fn._a2kit_pending_extra` does not exist (the attribute
  is never written, never read, and the `PENDING_EXTRA_ATTR`
  constant is removed from `a2kit.metadata`)

## REMOVED Requirements

### Requirement: Staging decorators communicate via `_a2kit_pending_extra`

**Reason**: Replaced by verb-decorator kwargs (`reports=`,
`enrichers=`). The side-channel attribute violated the "framework
reads what you wrote, never invents what is missing" ceiling
because a reader inspecting either decorator alone could not see
how configuration reached the meta.

**Migration**: Every `@reports(T)` call site folds into the adjacent
verb decorator as `reports=T`. Every `@enriches(fn)` call site
folds into `enrichers=(fn,)` (or onto the Router class attribute
per `router-conventions`). Remove `stage_extra` and
`PENDING_EXTRA_ATTR` from `a2kit.metadata`.
