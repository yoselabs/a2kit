## ADDED Requirements

### Requirement: `Principal` is a SCOPED provider when present

When a substrate produces a `Principal` for a request, the active `call_scope` SHALL carry it as a SCOPED provider. Tool bodies and `authorize=` callables SHALL be able to resolve `principal: Principal` by type annotation alone. The provider SHALL be written by the substrate adapter, not by author code. When no `Principal` is produced (e.g. unauthenticated path), the scope SHALL not register a `Principal` provider — type-annotated reads then raise the standard "no provider for type" container error.

#### Scenario: Scope carries Principal when authenticated

- **GIVEN** an authenticated request producing `Principal(subject="u1", ...)`
- **WHEN** the dispatch wrapper enters `call_scope`
- **THEN** `scope.get(Principal).subject == "u1"`
