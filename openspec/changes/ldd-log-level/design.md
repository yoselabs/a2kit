## Context

LDD primitives (`event` / `report` / `log` / `info` / `warning` / `error` / `debug`) read per-call state from a ContextVar bound by the dispatch site for the lifetime of one tool invocation. That ambient state already carries `events_enabled`, `sinks`, `tool_name`, `ctx`, and elapsed-timer state. The dispatch site (`fold_pipeline`) is where the App is in scope — that is where the level threshold gets read off `A2kitConfig` and stamped onto the per-call state.

Levels exist at the call site today: `log()` and the four level shorthands take a `Literal["debug" | "info" | "warning" | "error"]`. `event()` and `report()` do not — they're hardcoded to `info` on the wire. The threshold filter only buys real value if every emission has a comparable level, so the design extends `event()` / `report()` with an explicit `level` parameter (default `info`, preserving current behaviour).

## Goals / Non-Goals

**Goals:**
- One central filter in `emission.py` that drops emissions below threshold before any sink fan-out, ctx.log call, or wire serialization.
- Threshold sourced from `A2kitConfig.ldd.level`, configurable via `A2KIT_LDD__LEVEL` env (provider-chain default per ADR 0022).
- Every emission primitive (`event` / `report` / `log` / shorthands) participates uniformly.
- Filter applied in the dispatch site (read once per call), not per-emission (avoids contention on the config object inside hot loops).
- Add `trace` as a level below `debug`, so consumers wanting deep dispatch traces have headroom below the existing `debug` band.

**Non-Goals:**
- No change to sink fan-out shape (operator/wire split stays deferred).
- No promotion of operator sinks to defaults.
- No removal of `events_enabled` kill-switch — it stays as a hard off-switch independent of level.
- No package rename, no primitive fusion.
- No per-sink level (`stderr_level=info`, `wire_level=warn`) — single global threshold for v1.

## Decisions

### D1 — Threshold lives in `A2kitConfig.ldd.level`, not a separate engine

The provider-chain config engine (ADR 0022) is the right home. Adding a sibling settings tree would create two sources of truth for "consumer-overridable knobs" and undermine the recently established pattern.

Sub-model: `LddConfig(BaseModel)` with `level: LogLevel = "info"`. Env: `A2KIT_LDD__LEVEL`. Inverted source order (env > .env > kwargs > defaults) is inherited from `A2kitConfig.settings_customise_sources`.

**Alternative considered (rejected):** a separate `LddSettings` BaseSettings with its own env prefix. Rejected — two settings classes means two `.env` reads, two source-order customizations, and a maintenance burden every time the precedence rule changes.

### D2 — Filter at dispatch-site read, applied per-emission

`fold_pipeline`'s LDD-state stage reads `app.config.ldd.level` once when binding the ambient state, stamps it as `state.level_threshold: int` (numeric rank), and each emission primitive does `if rank(emission_level) < state.level_threshold: return` at the very top of the function, before any wire serialization.

**Why numeric ranks:** string compare is O(n), bench-irrelevant at any sane volume but semantically wrong; ranks make ordering explicit. Rank map: `trace=10, debug=20, info=30, warning=40, error=50`. Matches stdlib `logging` spacing (each level 10 apart leaves room for future levels like `notice=25` if needed).

**Alternative considered (rejected):** read `app.config.ldd.level` inside each emission. Rejected — requires every primitive to know how to reach the App, which means either a second ContextVar for the App or threading App through every primitive call. The per-call state already exists; one more field on it is cheap.

### D3 — `event()` and `report()` gain explicit `level` param (default `info`)

Today these are hardcoded `info` on the MCP wire. After: signature changes to `event(name, *, level="info", **fields)` and same for `report`. Existing callers (a2web's `event()`, the few `report()` sites) keep their behaviour at the default. Callers that want deeper traces flip to `event(..., level="debug")`.

**Alternative considered (rejected):** auto-promote `event()` to always `info` (no level param). Rejected — `event()` is the heaviest LDD primitive and the most likely candidate for "interesting at debug, noisy at info" tuning. Locking it to `info` forecloses that.

### D4 — Add `trace` level below `debug`

Consumers using `debug()` today expect it to be visible-when-debugging. Internal dispatch traces (router enter/exit, container resolve, etc.) want a level below that — they are noise even during routine debugging. `trace` gives a place to put them without re-tuning every existing `debug()` call.

`trace` is **not** added as a shorthand primitive in v1 (no `trace()` function); callers wanting it use `log("trace", ...)`. If trace emissions become common, a shorthand follows.

**Alternative considered (rejected):** map to stdlib `logging.DEBUG` = 10 and don't add `trace`. Rejected — leaves no headroom and forces internal dispatch traces to either spam `debug` or invent ad-hoc gating.

### D5 — Default level `info`, accept the breaking change

Picking `debug` as default preserves backward compatibility but defeats the proposal — consumers still drown in `debug()` emissions. `info` is the right default for production use; consumers wanting more flip the env var.

Mitigation: CHANGELOG `Breaking` entry, README config table, and a migration note saying "if your test suite or local dev relies on debug-level LDD output, set `A2KIT_LDD__LEVEL=debug` in `.env` or environment."

**Alternative considered (rejected):** default `debug`, document `info` as recommended. Rejected — sensible defaults beat documented advice; consumers who hit a problem will set the env var, consumers who don't won't.

### D6 — `events_enabled` boolean stays as orthogonal hard-off

The existing `--no-events` / `A2KIT_LDD=off` kill-switch stays — it serves a different question ("is LDD wired at all"). With threshold + kill-switch:

| `A2KIT_LDD` | `A2KIT_LDD__LEVEL` | Outcome |
|---|---|---|
| `on` (default) | `info` (default) | INFO+ emissions reach sinks |
| `on` | `debug` | DEBUG+ emissions reach sinks |
| `on` | `trace` | All emissions reach sinks |
| `off` | (any) | Nothing reaches sinks |

This matches the stdlib `logging` model exactly: a handler can be installed (events_enabled=on) but the threshold determines what gets through.

### D7 — Filter applies to *all* output channels (wire + sinks)

When a `log("debug", ...)` call is below threshold, the primitive returns before:
- calling `ctx.log(...)` (MCP wire)
- calling `ctx._emit(...)` (CLI stderr)
- dispatching to `state.sinks` (operator-side sinks)

This is the load-bearing invariant: the threshold is the volume control, period. Sinks don't get to override upward, callers don't get to bypass downward.

## Risks / Trade-offs

- **Risk:** consumers' test suites currently observe `debug()` output and break silently when the default `info` drops it.
  - **Mitigation:** explicit `BREAKING` entry in CHANGELOG; a passing test `tests/ldd/test_level_threshold.py::test_debug_dropped_by_default` makes the new behaviour discoverable; `.env` flip is one line.

- **Risk:** consumers add the same level to every `event()` call, defeating the proposal.
  - **Mitigation:** documentation in AGENTS.md provider-chain block calls out the smell ("if every emission is the same level, the level isn't doing work — promote consistently-noisy ones, demote consistently-quiet ones").

- **Risk:** scope creep — once levels are a knob, "per-sink levels," "per-tool levels," "wildcard filters" all become tempting.
  - **Mitigation:** non-goals list is explicit; LDD reshape in BACKLOG is the right venue for any of those if they prove necessary.

- **Trade-off:** adding `trace` widens the level vocabulary. A consumer writing a custom `LddSink` now has five level strings to potentially branch on, not four.
  - **Acceptance:** five is still small; stdlib `logging` has six (NOTSET/DEBUG/INFO/WARNING/ERROR/CRITICAL). The cost is one extra branch in custom sinks, which most consumers won't write at all.

## Migration Plan

1. Land `LddConfig` on `A2kitConfig` (additive — defaults preserve no-filter behaviour if level were `trace`, but default is `info` so this is the breaking step).
2. Land the filter in `emission.py`, including `event()` / `report()` signature extension.
3. CHANGELOG `Breaking` entry, README table, AGENTS.md block.
4. No consumer-side code changes required in a2kit. Consumer projects (a2web, a2sdlc, a2db, a2atlassian) self-migrate at their own pace — either set `A2KIT_LDD__LEVEL=debug` in dev `.env` files or audit their `debug()` calls and promote the useful ones to `info`.

Rollback strategy: if a consumer hits unexpected pain, they set `A2KIT_LDD__LEVEL=trace` and behaviour matches today (everything emits). No code rollback needed.

## Open Questions

None blocking. The "trace" rank value (10) and inter-level gap (10) follow stdlib `logging` conventions and don't need debate.
