---
id: "0022"
status: accepted
date: 2026-05-25
last_reviewed: 2026-05-25
supersedes: []
superseded_by: null
tags: [config, architecture, surface, governance, twelve-factor]
deciders: [Denis Tomilin]
---

# ADR 0022: Provider-chain configuration model — consumer always wins

## Status

Accepted, 2026-05-25.

## Summary

In the context of a2kit being one link in a chain of provider/consumer
relationships (a2kit → developer → consumer → end user), facing the
risk that any upstream link could permanently lock a downstream link
out of concerns that legitimately belong to that downstream link, we
decided to formally separate concerns by audience (a2kit-owned,
developer-owned, consumer-owned), require every consumer-owned concern
to be overridable from outside source code (env, `.env`, future YAML
or CLI sources) regardless of upstream choices, invert pydantic-settings'
default source order so env beats kwargs (consumer beats code), and
ship no public freeze/lock escape hatch, accepting that some developer
ergonomics ("lock this for my users") are explicitly unavailable and
must be implemented outside a2kit (env-strip at the process boundary,
wrapper layer), and that a2kit's own configuration surface models the
pattern developers are expected to apply to their own consumer-owned
concerns.

## Why

a2kit is not a leaf application. It is a framework that ships into
other people's deployments. Three observations make the audience split
load-bearing:

1. **The developer cannot know the consumer's environment.** Which
   MCP host fleet will receive the tools, which network the server
   binds to, which observability stack is in place, which secrets
   manager holds the credentials — none of this is knowable at code
   time. Hard-coding any of these in `App()` construction is wrong by
   construction.

2. **The chain recurses.** A developer who builds on a2kit then becomes
   a provider to their own consumer. If a2kit's pattern is "consumer
   beats code," the developer is expected to model the same pattern
   for their own consumer-owned concerns (their API keys, their
   feature flags, their rate limits). a2kit is the reference; the
   developer's own `Settings` class is the recursive instance.

3. **Pydantic-settings' default source order is wrong for this.**
   Out of the box, `init_settings` ranks above `env_settings`, which
   means kwargs in code win over env. That makes sense for an
   application's own config but is exactly backwards for a framework
   that wants `App("name", config=A2kitConfig(...))` to be a
   *suggestion*, not a *lock*.

The recent thread on MCP wire format (compat dual-emit vs strict
structured-only) made this concrete: the right setting depends on the
host fleet (Anthropic-native vs Cursor/Hermes/OpenClaw/Vercel-AI-SDK).
Only the consumer knows their fleet. A developer who hard-codes one
position via `App()` kwargs harms half of their downstream users.

## Decision

### Three audiences, three column owners

Every configurable concern in a2kit belongs to exactly one of:

| Audience | Owns | Examples |
|---|---|---|
| **a2kit (framework)** | Wire contract, schemas, dispatch, error envelope, type contracts | Envelope shape, ToolDescriptor schema, layer DAG |
| **Developer (app author)** | Tool surface, business logic, type annotations, error vocabulary, routing | Which tools exist, what they return, which `Raises` they declare |
| **Consumer (deployer/operator)** | Wire format compatibility, transport binding, observability, performance knobs, secrets | `mcp.structured_output`, log level, bind host, API keys |

A concern that legitimately spans audiences (e.g., the developer
*declares* a feature flag exists, the consumer *toggles* its state)
splits across columns: the schema is developer-owned; the value is
consumer-owned.

### The recursive rule

Every provider preserves the next consumer's control over their own
concerns. A provider may suggest defaults; a provider may not lock.

This applies to a2kit's relationship with developers AND to the
developer's relationship with their own consumer. a2kit models the
pattern; developers are expected to follow it.

### a2kit's concrete obligations

1. **Inverted source order.** A2kit's `Settings` classes customize
   pydantic-settings to put `env_settings` and `dotenv_settings`
   above `init_settings`. Env wins over code, every time. Defaults
   sit at the bottom of the stack.

2. **No freeze/lock surface.** No `frozen=True`, no `bypass_env=True`,
   no "developer-pinned" mode is exposed in any public API. If a
   developer's platform-of-platforms wants to constrain its downstream,
   it does so at the process boundary (env strip, wrapper, container
   policy), not through a2kit.

3. **Env-first docs.** Every consumer-owned config field documents
   the env var as the public API. The Python kwarg is dev convenience
   for tests and code-side defaults — secondary.

4. **A slot for developer-owned config, no merging.** a2kit provides
   `App.user_config` as an opaque pass-through that developers can
   populate with their own pydantic-settings instance, reachable from
   tool code via `container.app.user_config`. a2kit does not
   introspect it, does not merge it into `A2kitConfig`, does not
   validate it. The developer owns it end-to-end and is expected to
   apply the same env-beats-code pattern in their own `Settings`.

5. **Modeling, not enforcement.** a2kit lints its own code via
   convention and the layer DAG, but does NOT lint developer code to
   verify they follow the recursive pattern. The expectation lives
   in this ADR and in `AGENTS.md`; enforcement is review/culture.

### What this enables

- A developer writes `App("memory")` with no config. The consumer
  controls everything via env at deploy time.
- A developer writes `App("memory", config=A2kitConfig(mcp=McpConfig(
  structured_output=True)))` to suggest strict mode. The consumer
  who deploys with `A2KIT_MCP__STRUCTURED_OUTPUT=false` still gets
  compat mode. The developer's choice is a default; the consumer's
  is binding.
- A developer who needs deterministic config in tests clears
  `A2KIT_*` env vars in a fixture and constructs `A2kitConfig()`
  explicitly. Standard pytest pattern, no special framework support.

### What this explicitly disallows

- A developer cannot ship an a2kit-based App that locks a wire mode,
  a transport, a log level, or any other consumer-owned concern.
- A developer cannot prevent the consumer from setting an env var
  via any a2kit API.
- A developer who needs platform-level constraints (e.g., a SaaS
  running other people's a2kit apps under one wire policy) implements
  them outside a2kit at the process boundary.

## Consequences

### Positive

- Twelve-factor alignment by construction. Every deployment can be
  tuned without rebuild.
- Provider-chain coherence. The pattern a2kit models is the pattern
  developers replicate for their own consumers.
- Deploy-time host-fleet adaptation. The wire-mode lever (compat vs
  strict structured-only) becomes operationally meaningful — the
  team that owns the deployment owns the decision.
- ADR-citable rule for future changes. Any new surface that touches
  a consumer-owned concern is checked against this ADR for "is it
  env-reachable?"

### Negative

- Some developer ergonomics are gone. "Lock this for my users" is
  not available in a2kit API.
- A small surprise factor: developers who pass `config=...` kwargs
  and don't read the docs may be confused when env overrides their
  code. The env-first docstring convention is meant to forestall
  this, but it requires discipline.
- Tests must clear `A2KIT_*` env vars or rely on a fixture that does.
- Pydantic-settings' default source order is well-known; we diverge
  from it deliberately. New contributors must learn the inversion.

### Neutral

- The first concrete implementation of this ADR is the
  `a2kit-config-surface` change, which introduces `A2kitConfig`,
  `McpConfig`, the inverted source order, and the first
  consumer-owned knob (`mcp.structured_output`). Future ADRs and
  changes that touch consumer-owned concerns cite this ADR for the
  rationale.

## Alternatives considered

### A. Stay with the typical pydantic-settings precedence (kwargs win)

Rejected. It is the wrong default for a framework. Code-author choices
should be defaults, not locks. The whole motivating example (wire
compat mode) breaks under this model: the developer who picks one
position harms half of their downstream consumers.

### B. Expose an `experimental=True` posture flag instead of granular knobs

Considered and parked. The posture flag is elegant (one word, one
opt-in path) but does not survive contact with multiple
unrelated knobs — turning on "experimental" because you want token
savings shouldn't also turn on unrelated bleeding-edge behaviour.
Granular per-subsystem knobs scale better; if posture-level grouping
becomes valuable later, it can layer on top.

### C. Add a `freeze` / `lock` escape hatch for advanced developers

Rejected. Any such hatch breaks the recursive rule the moment a
developer uses it. If a platform needs to constrain its downstream,
the process boundary is the right enforcement point — env stripping,
container policy, wrapper layers — not a2kit's public API. Keeping
the hatch absent makes the principle absolute and the
implementation simple.

### D. Auto-adapt by `clientInfo.name` (per-client wire routing)

Rejected. Building and maintaining a compatibility matrix indexed
on MCP `clientInfo.name` is a tar pit: clients update support
quarterly, version-sensitive behaviour creeps in, unknown clients
default-to-wrong, the test surface explodes, and the registry rots
faster than it is maintained. The MCP ecosystem is converging on
structuredContent — building a compat layer for a temporary state
means running it in 2027 when nobody needs it.

### E. A general-purpose config engine that supports CLI + env + YAML on day 1

Considered for the implementing change but deferred. Pydantic-settings
gives env + `.env` + kwargs out of the box; that's enough for the
first knob and for prod deploys. YAML and CLI-flag bindings are
follow-up wedges that ride on the same precedence chain.

## References

- ADR 0004 (Package layout tiered by audience) — establishes the
  *surface* split by audience size. This ADR extends the audience
  model to *configuration*.
- ADR 0005 (Consumer feedback doctrine) — formalizes the framework
  ⇄ downstream-consumer feedback loop. This ADR sharpens the
  separation that doctrine assumes.
- ADR 0006 (No app override seam) — already establishes "no
  developer-side test override" for DI. This ADR generalizes the
  principle: no developer-side override of consumer-owned concerns
  in any surface.
- ADR 0017 (One public App) — preserves one public surface for the
  developer. This ADR preserves one public surface for the consumer
  (env-first).
- Pydantic-settings docs — `settings_customise_sources` is the
  mechanism that implements the inversion.
- The Twelve-Factor App, §III "Config" — the deployment-time-config
  principle this ADR ports into a2kit.
