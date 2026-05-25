## Why

Recent config wave (ADR 0022) landed `A2kitConfig` with sub-configs (`ldd`,
`mcp`). Subsystems now reach into `app.config.ldd.level` /
`app.config.mcp.structured_output` directly inside hot dispatch paths and
build-time wiring (`stages.py:270`, `mcp/server.py:368`,
`http/build.py`). This couples every subsystem to `A2kitConfig`'s
attribute shape, defeats the consumer-feedback doctrine for per-test
rebinding, and creates two parallel access paths
(`app.debug` proxy vs `app.config.debug`). The BACKLOG already parks
"DI-for-sub-configs"; the structural coherence audit (2026-05-25)
ranked this the #1 leverage move.

## What Changes

- Register `A2kitConfig` and each sub-config (`LddConfig`, `McpConfig`,
  and any future sub-config) in the DI container at `App.__init__`.
- Subsystems consume config via DI dependency on the sub-config type
  (e.g. `ldd_config: LddConfig`), not by walking `app.config.ldd`.
- `stages.LddStateStage` captures `LddConfig` once at stage construction
  (or resolves per-call from container) instead of reading
  `app.config.ldd.level` inside the wrapper.
- `mcp/server.py` and `http/build.py` resolve their config dependency
  through DI at build time.
- **BREAKING (internal)**: `App.config.<sub>` direct reads from
  `src/a2kit/packages/**` are removed; the public `App.config` attribute
  remains for consumer-side override discovery.
- Retire the `App.debug` proxy attribute in favour of resolving
  `A2kitConfig` from DI when needed (already migrated to config; remove
  the convenience alias).

## Capabilities

### New Capabilities

- `config-di-providers`: A2kitConfig and each sub-config are
  DI-registered providers; subsystems consume by type, not by
  attribute walk.

### Modified Capabilities

- `runtime-config`: documents that A2kitConfig and sub-configs are
  registered in the container and the override path is rebind, not
  attribute mutation; the `App.debug` proxy clause is removed from
  the canonical debug requirement.
- `core-composition`: the `App.debug` attribute clause is removed; the
  composition surface no longer carries the proxy attribute, only
  `app.config`.
- `di-container-package`: adds the framework's own config providers
  as a documented seed-time registration.
- `ldd-level-threshold`: LDD threshold resolved via `LddConfig`
  injection rather than direct `app.config.ldd.level`.

## Impact

- Affected code: `src/a2kit/app.py`, `src/a2kit/config.py`,
  `src/a2kit/packages/dispatch/stages.py`,
  `src/a2kit/packages/mcp/server.py`,
  `src/a2kit/packages/http/build.py`, `src/a2kit/packages/ldd/`.
- API: `App.debug` removed (internal users only); `App.config`
  preserved.
- Dependencies: no new dependencies; reuses existing DI container.
- Tests: per-test override of config via container rebind (replaces
  current monkeypatching of `app.config.debug = True` in fixtures).
