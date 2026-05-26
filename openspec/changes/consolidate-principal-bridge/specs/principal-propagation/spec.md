## MODIFIED Requirements

### Requirement: DI is the single source of truth for Principal

`Principal` SHALL be resolvable in tool bodies and `authorize=`
callables exclusively via the per-call DI scope. The dispatch
pipeline seeds Principal into the scope via the explicit
`Container.seed_scoped(Principal, p)` API, with `p` obtained from
the named bridge (`current_request_principal()`).

There SHALL be no other "ambient lookup" path inside the dispatch
pipeline: no `_a2kit_request_principal.get()` direct reads in stage
code, no `next((v for v in kwargs.values() if isinstance(v, Principal)))`
scan-and-stuff dance, no magic wire-key (`"_a2kit_principal"`) seed.

#### Scenario: Tool body resolves Principal via DI override

- **GIVEN** an `App` with `app.container().provide(Principal, lambda: fake_principal)`
- **WHEN** a tool decorated `async def me(*, principal: Principal) -> ...`
  is dispatched
- **THEN** the tool body receives `fake_principal`
- **AND** dispatch source code contains no `kwargs.values()` scan for
  Principal instances and no magic wire-key seed

#### Scenario: No substrate publication and no DI provider — clear error

- **GIVEN** an `App` with no `Principal` provider and a synthetic
  dispatch path where no substrate has called `set_request_principal`
- **WHEN** a tool body declaring `principal: Principal` is dispatched
- **THEN** the dispatcher raises a clear "no provider for Principal"
  error
- **AND** the error does not silently fall back to a ContextVar or
  a kwargs scan

#### Scenario: Substrate publication flows via the named bridge

- **GIVEN** a substrate middleware that calls
  `set_request_principal(p)` at the authentication boundary
- **WHEN** a downstream tool body declaring `principal: Principal`
  is dispatched
- **THEN** the tool body receives `p`
- **AND** the path inside the dispatch pipeline is:
  `current_request_principal()` → `child.seed_scoped(Principal, p)` →
  DI resolution by type

## REMOVED Requirements

### Requirement: Principal seeding uses the implicit wire-by-type mechanism

**Reason**: The previous implementation seeded Principal into the
DI scope by placing it into `wire_kwargs` under the magic key
`"_a2kit_principal"`. `Container.call_scope` then walked
`wire.values()` and registered each value's `type(value)` as a SCOPED
provider as a side effect. This was invisible at call sites and made
the wire-key string load-bearing in a way that hid the actual DI
registration.

**Migration**: callers that previously relied on
`wire_kwargs.setdefault("_a2kit_principal", p)` (e.g.,
`dispatch.substrate._lift_principal_into_scope`,
`packages/dispatch/_principal_scope.seed_principal_into_wire`) now
publish via the explicit `Container.seed_scoped(Principal, p)` API
on the child container they're seeding. The magic wire key is
removed.
