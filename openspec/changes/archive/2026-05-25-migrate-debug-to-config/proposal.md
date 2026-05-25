## Why

`App(debug=True)` is today's most visible violation of ADR 0022's
provider-chain rule: it locks the consumer out of disabling debug at
deploy time. A developer who hard-codes `App("svc", debug=True)` in
source ships a binary the consumer cannot quiet without forking.
ADR 0022 forbids this. The `a2kit-config-surface` change landed the
engine; this change uses it for the canonical consumer-owned concern.
Bundled with the change: the long-deferred README "Configuration"
section + AGENTS.md env-first paragraph (which would have lived in
config-surface but were scoped out to keep that change tight).

## What Changes

- **BREAKING**: Remove `debug` kwarg from `App.__init__`. Existing
  `App("name", debug=True)` raises `TypeError` with a migration hint
  pointing at `A2KIT_DEBUG=true` and `A2kitConfig(debug=True)`.
- **NEW**: `A2kitConfig.debug: bool = False` top-level field. Env:
  `A2KIT_DEBUG=true`. Reachable via `app.config.debug`.
- **MIGRATE**: Internal reads of `app.debug` → `app.config.debug`.
  `AppRuntime.debug` is fed from `app.config.debug` at build time.
- **DOCS**: README gains "Configuration" section with the ADR 0022
  precedence diagram, the `A2KIT_<SUBSYSTEM>__<KNOB>` env convention,
  and `A2KIT_DEBUG` + `A2KIT_MCP__STRUCTURED_OUTPUT` as worked
  examples.
- **DOCS**: AGENTS.md "Patterns" section gains one paragraph on
  env-first configuration pointing at ADR 0022.
- **DOCS**: ANTIPATTERNS.md gains an entry "Hard-coding consumer
  concerns in App() construction" with the debug kwarg removal as
  the canonical example.
- **TESTS**: Test sites that pass `debug=True` to `App(...)` migrate
  to `A2kitConfig(debug=True)` or `monkeypatch.setenv("A2KIT_DEBUG", "true")`.
- **NO**: `App.debug` attribute itself is preserved (read from
  `config.debug` at construction). External code that reads
  `app.debug` continues to work without rewrite. The breaking surface
  is the *kwarg*, not the attribute.

## Capabilities

### Modified Capabilities

- `core-composition`: `App.__init__` signature loses `debug` kwarg.
  `App.debug` attribute remains, sourced from `config.debug`.
- `operational-contracts`: scenarios that say "`App(debug=True)`"
  reword to "`A2kitConfig(debug=True)`" or "`A2KIT_DEBUG=true`". The
  behavior contracts (envelope traceback, CLI stderr) are unchanged.
- `runtime-config`: add `debug` as a documented top-level field.

## Impact

- **Code**: `src/a2kit/app.py` (kwarg removal, sourced from config),
  `src/a2kit/runtime.py` (continues reading `app.debug` —
  no change required if the attribute proxies to config).
- **APIs**: `App.__init__` is the breaking surface. Attribute access
  is preserved.
- **Tests**: ~6 sites under `tests/` migrate.
- **Docs**: README, AGENTS.md, ANTIPATTERNS.md, OPERATIONAL_CONTRACTS
  (citation cleanup), ADRs 0017/0019 (surface tables).
- **Consumer repos** (a2web, a2atlassian, a2db, a2skill, a2sdlc):
  any call site passing `debug=True` to `App()` migrates per-repo
  in follow-up PRs. Pure mechanical rewrite.
