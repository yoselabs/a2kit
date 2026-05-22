## MODIFIED Requirements

### Requirement: Descriptor build is one-shot

Descriptors SHALL be built once per tool, at registration time, and `App.tools()` SHALL return the cached descriptors without re-running type inference.

Subsequent calls to `App.tools()` SHALL return the descriptors materialized at registration time. There is no separate `tool_descriptors()` accessor — `App.tools()` is the single tool-introspection API, and it is the call that returns cached descriptors.

#### Scenario: No work on repeated lookups

- **GIVEN** an app with N registered tools
- **WHEN** `app.tools()` is called K times
- **THEN** type inference (`typing.get_type_hints` and the inference walker) is invoked exactly N times in total — once per tool at registration
