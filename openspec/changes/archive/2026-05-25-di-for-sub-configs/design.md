## Context

`A2kitConfig` (ADR 0022) ships with sub-configs (`ldd`, `mcp`, `http`,
`cli`). Subsystems currently read config by walking attributes on a
captured `app` reference (`app.config.ldd.level` inside
`LddStateStage.wrap`, `app.config.mcp.structured_output` inside
`mcp/server.py`). This is import-graph clean (no layer violations) but
runtime-coupling unclean: every subsystem encodes the full path to its
knob, every test that needs a per-call override monkeypatches a private
attribute, and the `App.debug` proxy duplicates `App.config.debug`.

The coherence audit (2026-05-25) identified this as the highest-leverage
structural debt landed by the recent config wave; BACKLOG already parks
"DI-for-sub-configs".

The DI container already ships per-call scoping (ADR 0009) and lazy
resolution (ADR 0008). Adding config providers reuses both.

## Goals / Non-Goals

**Goals:**
- One uniform way for any subsystem to obtain its config: declare a
  typed parameter and let the container resolve it.
- Per-test rebind via `app.provide(LddConfig, fake)` rather than
  monkeypatching `app.config.ldd`.
- Retire the `App.debug` shortcut so there is one access path
  (`A2kitConfig` via DI).
- Preserve the public `App.config` attribute for consumer-side override
  discovery (no behaviour change for consumers).

**Non-Goals:**
- Restructuring `A2kitConfig`'s pydantic-settings source ordering (ADR
  0022 is settled).
- Introducing a config event/observer system. Sub-configs are immutable
  per-runtime; reads are point-in-time at stage construction or per
  call.
- Migrating consumer downstream `Settings` patterns. The change is
  internal-only.

## Decisions

### 1. Each sub-config is a separate provider, plus `A2kitConfig` itself

Register four providers at `App.__init__`:
- `A2kitConfig` → resolves to `self.config`
- `LddConfig` → resolves to `self.config.ldd`
- `McpConfig` → resolves to `self.config.mcp`
- (future sub-configs follow the same pattern)

Rationale: subsystems declare the tightest type they need; the container
constructs the dependency graph; future sub-configs slot in by adding a
provider line without editing every consumer.

Alternative considered: register only `A2kitConfig` and let subsystems
walk `.ldd` / `.mcp`. Rejected — same attribute-walk coupling, just
funneled through DI.

### 2. Stage-time capture for hot-path reads

`LddStateStage` (and any future per-call stage) accepts its config in
the constructor: `LddStateStage(ldd_config: LddConfig)`. The pipeline
construction site resolves it once. Per-call reads inside `.wrap()` use
the captured value, not a container lookup.

Rationale: the dispatch pipeline is built once at `App` build time;
per-call container traversal would be wasted work. Stage-time capture
matches how `DISPATCH_PIPELINE` already composes.

Alternative considered: make every stage resolve its config via the
container per call. Rejected on perf and ergonomics; the value cannot
change between dispatches anyway (config is per-runtime).

### 3. Transport builders resolve at build time

`mcp/server.py:build_mcp_server` and `http/build.py:build_http_app`
resolve `McpConfig` / `HttpConfig` from the container at the top of the
builder, before tool registration. Pass the resolved value down via
plain argument or closure capture.

Rationale: builders run once; the container is the seam.

### 4. `App.debug` removed; `A2kitConfig.debug` is canonical

`App.debug` shortcut is deleted. The two internal call sites that read
it switch to resolving `A2kitConfig` from the container (CLI traceback
path, MCP envelope path). Public `App.config` remains.

Rationale: the proxy was a transitional convenience; keeping it forks
behaviour into two attribute paths and confuses test fixtures.

### 5. AGENTS.md "loud crash" applies to the proxy removal

`App.debug` access on a constructed App raises `AttributeError` with a
migration hint pointing at `app.config.debug` (consumer-side
introspection) or the DI provider (subsystem-side resolution).

## Risks / Trade-offs

- **[Risk] Stage-time capture freezes config at build time** → Mitigation:
  document explicitly that A2kitConfig is immutable per-runtime (already
  the de-facto reality; this just makes it normative). Test fixtures
  that swap config rebuild the App.
- **[Risk] Internal callers of `App.debug` may exist in tests** →
  Mitigation: grep before landing; the loud-crash migration hint catches
  any straggler at runtime.
- **[Risk] Adding sub-configs in the future requires editing
  `App.__init__` to register the provider** → Mitigation: small loop
  over a known list of sub-config types; documented in design. A
  future change can derive this from `A2kitConfig`'s pydantic schema if
  the count grows.
- **[Trade-off] Subsystems gain a DI dependency they didn't have before**
  → Accepted: DI is already the framework's wiring story; this aligns
  config with every other framework-provided dependency.

## Migration Plan

1. Add config providers to `App.__init__`. No subsystem changes yet —
   container exposes them, nothing consumes.
2. Migrate `LddStateStage` to accept `LddConfig` in constructor; update
   pipeline construction.
3. Migrate `mcp/server.py` to resolve `McpConfig` from container at
   build time; remove `app.config.mcp.*` reads.
4. Migrate `http/build.py` likewise for `HttpConfig`.
5. Remove `App.debug` attribute; migrate the two internal call sites to
   resolve `A2kitConfig` via container.
6. Add `App.__getattr__` raising on `debug` with a migration hint.
7. Update tests: replace `monkeypatch.setattr(app.config, ...)` with
   `app.provide(SubConfig, fake)` patterns.

Rollback: revert in reverse; `A2kitConfig` itself is unchanged so no
data-shape rollback needed.

## Open Questions

- Should we register sub-configs as singletons (resolved once at first
  ask) or as factories (resolved every ask)? Leaning singleton — they
  are immutable per-runtime. Confirm with the DI container's default
  semantics during implementation.
