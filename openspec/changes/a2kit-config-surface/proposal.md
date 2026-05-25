## Why

a2kit's runtime concerns (wire format compatibility, debug verbosity, future
log level / telemetry / rate limits) are scattered across constructor kwargs,
ad-hoc env reads, and CLI flags on `a2kit serve`. There is no unified
config surface, and — more critically — there is no rule that *consumer*
concerns (the team deploying the App) override *developer* choices (the team
that wrote it). ADR 0022 formalises the provider-chain configuration model
and requires "env beats code, no freeze hatch." This change is the first
concrete implementation of that ADR, motivated immediately by the typed-error
work landing structuredContent on success — a setting whose right value
depends on the host fleet, which only the consumer knows.

## What Changes

- **NEW**: `a2kit.config.A2kitConfig` (pydantic-settings) with
  `McpConfig`, `HttpConfig`, `CliConfig` sub-models. Inverted source order:
  `env > .env > init kwargs > field defaults` (consumer beats code).
- **NEW**: `A2KIT_*` env var convention with double-underscore nesting
  (`A2KIT_MCP__STRUCTURED_OUTPUT=true`). Documented as the public API.
- **NEW**: First consumer-owned knob — `mcp.structured_output: bool = False`.
  Default `False` keeps spec-compliant dual-emit (works everywhere).
  `True` flips success path to structured-only with a short content[]
  marker (saves ~50% tokens on hosts that forward structuredContent;
  degrades Cursor, Hermes, OpenClaw, Kiro, Vercel-AI-SDK consumers).
- **NEW**: `App.user_config: Any` opaque pass-through slot for the
  developer's own pydantic-settings instance, reachable via
  `container.app.user_config`. a2kit does not introspect, merge, or
  validate it.
- **DEFERRED**: `App.debug` migration. The kwarg stays as-is in this
  change to keep scope tight. A follow-up change (`migrate-debug-to-
  config`) will remove the kwarg and route it through `config.debug`
  once the engine has shipped. The principle (consumer beats code)
  is already enforced for the new knobs.
- **NEW**: Wire format branch in `mcp/_wrappers.py` reads
  `app.config.mcp.structured_output` to pick dual-emit vs strict.
- **NO public freeze/lock surface.** ADR 0022 forbids it.

## Capabilities

### New Capabilities

- `runtime-config`: pydantic-settings based configuration surface for
  a2kit, defining the inverted source order (env > code), the
  `A2KIT_*` env var convention, the `A2kitConfig` schema (a2kit-owned
  knobs only), the `App.user_config` slot (developer-owned, opaque),
  and the rule that no public API may lock a consumer-owned concern.

### Modified Capabilities

- `core-composition`: `App.__init__` signature changes — `debug` kwarg
  removed, optional `config: A2kitConfig | None = None` added, optional
  `user_config: Any = None` added.

(The MCP success-path wire shape is a new behaviour governed entirely
by the new `runtime-config` capability; no existing wire-format spec
is modified.)

## Impact

- **Code**: `src/a2kit/__init__.py` (exports), `src/a2kit/runtime/app.py`
  (constructor, config field, user_config slot), new `src/a2kit/config.py`
  module, `src/a2kit/packages/mcp/_wrappers.py` (wire branch), every
  test/fixture that constructs `App(debug=True)`.
- **APIs**: `App` signature change is the breaking surface. All other
  changes are additive.
- **Dependencies**: adds `pydantic-settings` to `a2kit`'s required deps
  (already transitively present via pydantic ecosystem; promoting to
  explicit).
- **Consumers**: a2web, a2atlassian, a2db, a2skill, a2sdlc — any call
  site that passes `debug=True` to `App()` must migrate. Mechanical
  rewrite. No semantic change in behaviour at the default.
- **Docs**: ADR 0022 cited from `README.md` "Configuration" section
  (new), AGENTS.md gets a one-paragraph block on the env-first
  convention.
- **Tests**: new fixture `_clear_a2kit_env` (autouse-eligible) to
  isolate tests from ambient env. New tests assert
  env-beats-kwarg, .env loading, default values, and the wire branch
  selection.
