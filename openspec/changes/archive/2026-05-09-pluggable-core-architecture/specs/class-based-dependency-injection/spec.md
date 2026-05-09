## MODIFIED Requirements

### Requirement: `Depends(<class>)` resolution flows through plugin-contributed resolvers

The mechanism for `Depends(<class>)` resolution remains identical at
the call site. Tools declare `*, conn: TrackerConn = Depends(TrackerConn)`
and the runtime injects the loaded conn at invocation. The
**implementation** moves out of core: the resolution code lives in
the `Connections` plugin under
`a2kit.packages.connections.di::bind_class_dependencies`.

The CLI / MCP builders SHALL apply class-deps binding by walking
`app.depends_resolvers()` rather than calling
`a2kit.signature.bind_class_dependencies` directly. Each resolver
exposes:

- `claim(target: Any) -> bool` — does this resolver handle this
  `Depends(...)` target?
- `async resolve(target: Any, kwargs: dict, app: App) -> Any` — return
  the resolved value.

The Connections plugin contributes:

- A resolver for `target` ∈ registered conn classes — returns the
  loaded conn for `kwargs["connection"]`.
- A resolver for `target` ∈ store classes (declared via Generic or
  class-attribute) — returns `target(loaded_conn)`.

#### Scenario: Depends(ConnT) resolution — call-site behavior unchanged
- **WHEN** a tool has `*, conn: TrackerConn = Depends(TrackerConn), connection: str` and is invoked with `connection="default"`
- **THEN** the runtime injects the loaded `TrackerConn` instance, identical to today

#### Scenario: Resolution requires Connections plugin
- **WHEN** the App has no `Connections` plugin and a tool uses `Depends(TrackerConn)`
- **THEN** at `app.tools()` time the runtime raises with a clear "no resolver claims this target" error, listing registered resolver-contributors

#### Scenario: Multiple plugins can contribute resolvers
- **WHEN** Plugin A claims conn classes and Plugin B claims store classes (both registered)
- **THEN** the runtime picks the resolver whose `claim(target)` returns True; if multiple plugins claim the same target, the first-registered wins
