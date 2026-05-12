# tool-descriptors — explicit-router-surface delta

## MODIFIED Requirements

### Requirement: Descriptors read per-tool extras from verb-decorator kwargs only

Descriptor materialization SHALL read per-tool extras (e.g. `a2kit.report_type`, `a2kit.tool_enrichers`) only from `A2KitMeta.extra` populated by verb-decorator kwargs, when `App.tool_descriptors()` runs. The descriptor materializer SHALL NOT consult any
side-channel attribute on the wrapped function (the
`_a2kit_pending_extra` path is removed).

Behaviour is otherwise unchanged: descriptors are still built
one-shot at registration time, still expose `name`, `router`,
`fn`, `return_type`, and `format_hint`, and still resolve
forward references via `typing.get_type_hints(..., include_extras=True)`.

#### Scenario: Descriptor sees `reports=` kwarg

- **GIVEN** a router tool decorated `@a2kit.read(reports=Task)`
- **WHEN** the router is added to an app and
  `app.tool_descriptors()` is called
- **THEN** the descriptor's underlying `A2KitMeta.extra` carries
  `"a2kit.report_type": Task` and that value is sourced from the
  verb-decorator kwarg path (not from `_a2kit_pending_extra`,
  which no longer exists)

#### Scenario: No staged-extra inspection

- **WHEN** descriptor materialization runs for any tool
- **THEN** it does not call `getattr(fn, "_a2kit_pending_extra", ...)`
  or any equivalent side-channel read
