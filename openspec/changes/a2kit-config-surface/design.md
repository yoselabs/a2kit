## Context

a2kit ships into other people's deployments. Today, runtime concerns are
scattered: `App(debug=True)` lives as a constructor kwarg; transport
choice lives as a `serve` CLI flag; auth credentials live in env by
convention; nothing routes the wire format. The `a2effect-foundation`
change just landed `structuredContent` on success — a setting whose
right value depends on the host fleet (Anthropic-native fleets prefer
strict structured-only for token savings; Cursor / Hermes / OpenClaw /
Vercel-AI-SDK consumers need dual-emit fallback). Only the consumer
knows their fleet, so this setting must be controllable from outside
source code.

ADR 0022 (Provider-chain configuration model) was authored 2026-05-25
to formalise this: env beats code, no freeze hatch, recursive pattern
that developers replicate for their own config. This change is the
first concrete implementation of ADR 0022.

## Goals / Non-Goals

**Goals:**
- One unified pydantic-settings-based config surface (`A2kitConfig`)
  for all consumer-owned runtime knobs.
- Inverted source order so env > .env > kwargs > defaults. Consumer
  wins, always.
- First knob: `mcp.structured_output` (default False = compat).
- `App.user_config` slot for the developer's own settings, opaque to
  a2kit.
- Migrate `App.debug` under `config.debug` to consolidate one existing
  scattered concern (acts as a worked example of the migration shape).
- Env var convention: `A2KIT_<SUBSYSTEM>__<KNOB>` with double-underscore
  nesting (pydantic-settings idiomatic).

**Non-Goals:**
- YAML loader. Deferred until a second use case appears.
- CLI flag bindings on `a2kit serve` for the new knobs. Deferred until
  someone asks; env covers prod, kwargs cover tests, `.env` covers dev.
- Migration of transport/bind-host/bind-port from CLI flags into
  `A2kitConfig`. They are operator-time concerns and stay on the CLI.
- Per-router or per-tool config overrides. The wire format is a
  process-wide concern.
- Lint rules to enforce the recursive pattern on developer code. ADR
  0022 documents the expectation; enforcement is review/culture.
- A general posture flag (`experimental=True`). Parked per ADR 0022
  Alternative B.

## Decisions

### D1. pydantic-settings as the engine

We already use pydantic everywhere. `pydantic-settings` gives env +
`.env` + kwargs + custom sources out of the box. Reaching for anything
else (dynaconf, omegaconf, hand-rolled) buys nothing and adds a dep.

Alternative considered: hand-roll `os.environ.get` plumbing. Rejected —
it works for one knob but breaks down at three (nested structures,
type coercion, .env support, validation).

### D2. Inverted source order (env beats init)

Pydantic-settings default puts `init_settings` first. We invert via
`settings_customise_sources`:

```python
return env_settings, dotenv_settings, init_settings, file_secret_settings
```

This is the load-bearing decision from ADR 0022. Without it, the
developer's kwarg would lock the consumer out — exactly what the ADR
forbids.

Alternative considered: keep pydantic's default and tell developers
"don't pass kwargs that lock things." Rejected — relies on discipline,
fails by construction. The framework must guarantee the guarantee.

### D3. Double-underscore nesting (`A2KIT_MCP__STRUCTURED_OUTPUT`)

Pydantic-settings uses `env_nested_delimiter`. Single `_` collides
with snake_case field names; double `__` is the idiomatic shape every
pydantic-settings shop converges on. Slightly weird-looking on first
encounter, but unambiguous and consistent across the future taxonomy.

Alternative considered: flat env vars with no nesting
(`A2KIT_MCP_STRUCTURED_OUTPUT` mapping to top-level
`mcp_structured_output`). Rejected — loses the grouping that
sub-models provide and breaks down once the config has 10+ knobs.

### D4. First knob default = compat (False)

`mcp.structured_output: bool = False` means the default behaviour
is spec-compliant dual-emit: structuredContent + content[] both carry
the payload. Works on every MCP host. Pay 2x tokens on smart hosts.

Setting True flips to strict structured-only with a short
content[] marker — saves tokens on Anthropic/ChatGPT/Codex/Copilot
but degrades on Cursor / Hermes / OpenClaw / Kiro / Vercel-AI-SDK.

The safe default prevents silent regressions on the long tail of
consumers; the opt-in is for fleets that know they only target
modern hosts.

Alternative considered: True (strict by default). Rejected — breaks
non-trivial parts of the MCP ecosystem on first deploy.

### D5. `App.debug` migrates under `config.debug` (BREAKING)

`App(debug=True)` is removed. New surface: env `A2KIT_DEBUG=true` or
`A2kitConfig(debug=True)`. No kwarg shim.

This serves two purposes:
1. Validates the migration shape (one consumer-owned concern moves
   under the unified surface) before we accumulate more knobs.
2. Removes a present-day footgun: the current `debug=True` kwarg
   locks the consumer out of disabling debug at deploy time. Today's
   behaviour is a live example of the anti-pattern ADR 0022 forbids.

Alternative considered: keep `debug` kwarg AND add `config.debug`.
Rejected — two surfaces for one concern, "no redundancy" principle.

### D6. `App.user_config: Any` (opaque slot)

A2kit does not introspect the developer's own config. The slot is
typed `Any` (or perhaps `BaseModel | None` for documentation; same
thing operationally). Reachable via `app.user_config` and
`container.app.user_config`.

a2kit deliberately does NOT:
- Merge `user_config` into `A2kitConfig`.
- Validate the type.
- Read env vars on the developer's behalf.

The developer constructs their own `MyAppConfig(BaseSettings)`,
applies the same env-beats-code pattern in their own
`settings_customise_sources`, and passes the instance into `App`.
a2kit is the reference; the developer's class is the recursive
instance per ADR 0022.

Alternative considered: a `register_namespace("myapp", MyAppConfig)`
extension point that merges into `A2kitConfig` under `A2KIT_MYAPP__*`.
Rejected — forces the `A2KIT_` prefix onto developer-owned env vars
(wrong namespace) and creates a hidden coupling.

### D7. No public freeze/lock surface (load-bearing per ADR 0022)

No `frozen=True`, no `bypass_env=True`, no developer-pinned mode is
exposed in any documented API. Tests that need determinism use
`monkeypatch.delenv` in a fixture; SaaS layers that need to constrain
downstream do so at the process boundary (env-strip, container
policy), outside a2kit.

### D8. Wire branch lives in `_wrappers.py`, reads `app.config.mcp`

The success-path wire format selection is a single branch in the
existing FastMCP result wrapper. The branch reads
`app.config.mcp.structured_output` and picks between dual-emit
(today's behaviour) and strict-mode. Both render paths are
unit-tested.

Alternative considered: wire format as a pluggable strategy class.
Rejected — premature abstraction for two cases that will likely
stay two.

## Risks / Trade-offs

- **Risk**: Tests with ambient `A2KIT_*` env vars produce
  non-deterministic results.
  **Mitigation**: Ship an autouse-eligible `_clear_a2kit_env` fixture
  in `tests/conftest.py`. Document the pattern in AGENTS.md.

- **Risk**: Developers who pass `config=A2kitConfig(...)` are
  confused when env overrides their kwarg.
  **Mitigation**: Every field's docstring leads with the env var as
  the public API; the kwarg is documented as "dev convenience for
  tests and code defaults." README configuration section explains
  precedence chain with a diagram.

- **Risk**: `pydantic-settings` source order divergence surprises
  contributors familiar with the default.
  **Mitigation**: Inline comment on `settings_customise_sources`
  citing ADR 0022. AGENTS.md mentions the inversion.

- **Risk**: BREAKING `App.debug` removal hits ~5–10 call sites
  across consumer repos (a2web, a2atlassian, a2db, a2skill).
  **Mitigation**: Mechanical rewrite. Tracked per-repo as a separate
  migration item once this change lands. No semantic behaviour change
  at the default value.

- **Risk**: First-knob default (False = compat) means smart-host
  deployments still pay 2x tokens unless someone flips the env var.
  **Mitigation**: Document the env var prominently in the migration
  notes and the README "Configuration" section. The whole point of
  the env-first surface is that consumers can flip it without code
  changes — that's a feature, not a problem.

- **Risk**: Future YAML / CLI source addition could conflict with
  the inverted source order if done carelessly.
  **Mitigation**: ADR 0022 locks the precedence chain
  (CLI > env > .env > YAML > init > defaults). Any future addition
  slots in by position; the rule "closer-to-operator = higher" makes
  the placement unambiguous.

## Migration Plan

1. Land this change in a single PR (per AGENTS.md "no PRs for solo
   repos — merge to main directly"). Mechanical: introduce
   `A2kitConfig`, wire `App.__init__` and `App.user_config`, migrate
   `_wrappers.py` to read `app.config.mcp.structured_output`, remove
   `App.debug` kwarg, add tests.
2. Update consumer repos (a2web, a2atlassian, a2db, a2skill, a2sdlc)
   in follow-up PRs per-repo: replace `App(debug=True)` with
   `A2KIT_DEBUG=true` in `.env` or `A2kitConfig(debug=True)` in
   composition root. Each repo's migration is independent; no
   coordination needed.
3. AGENTS.md gets a one-paragraph block on the env-first convention
   pointing at ADR 0022.
4. README gains a "Configuration" section with the precedence
   diagram and the `A2KIT_MCP__STRUCTURED_OUTPUT` worked example.
5. ADR 0022 status flips from `proposed` to `accepted` once this
   change lands.

No rollback strategy needed — the change is additive at the env
surface (default behaviour preserved) and BREAKING only at one
kwarg (mechanical migration).

## Open Questions

None. The design is settled by ADR 0022 + this document. Future
expansion (YAML, CLI flags, additional knobs) is documented as
non-goal here and tracked in BACKLOG.
