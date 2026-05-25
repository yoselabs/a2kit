## ADDED Requirements

### Requirement: DI is the single source of truth for Principal

`Principal` SHALL be resolvable exclusively via the per-call DI scope. No dispatch-pipeline stage MAY read `Principal` from a contextvar (or any other ambient mechanism) as a fallback. Substrate adapters MUST write `Principal` into the per-call DI scope; how the substrate obtains it from the wire (header, OAuth token, OIDC claim) is the adapter's private concern.

#### Scenario: Tool body resolves Principal via DI override

- **GIVEN** an App with a DI provider registered for `Principal` returning a `fake_principal`
- **WHEN** a tool decorated `async def me(*, principal: Principal) -> Principal: return principal` is dispatched
- **THEN** the tool body receives `fake_principal`
- **AND** no contextvar was set or read during dispatch

#### Scenario: No provider, no substrate write — clear error

- **GIVEN** an App with no Principal provider and a synthetic dispatch path that does not write Principal into the scope
- **WHEN** a tool body declaring `principal: Principal` is dispatched
- **THEN** the dispatcher raises a clear "no provider for Principal" error
- **AND** the error does not silently fall back to a contextvar

## REMOVED Requirements

### Requirement: Contextvar fallback for Principal resolution

**Reason**: Dual-path threading (DI scope plus `_a2kit_request_principal` ContextVar) created cognitive load and hid the data path. The DI scope is the canonical mechanism per `principal-propagation`; the contextvar was belt-and-braces left over from an earlier iteration.

**Migration**: Any code reading `_a2kit_request_principal` MUST migrate to `call_scope.resolve(Principal)` or accept `principal: Principal` as a typed dependency. Substrate adapters MUST write Principal into the DI scope directly at the substrate's authentication boundary.
