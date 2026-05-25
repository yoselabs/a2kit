## Why

LDD emissions already carry levels at the call site (`log("debug"|"info"|"warning"|"error", ...)` plus the `debug/info/warning/error` shorthands), but nothing filters by level — every emission reaches every sink. Today the only volume control is "is LDD wired at all," which is too coarse: a2web's `event()` calls are routinely useful, the per-step `debug()` traces a2sdlc emits are not, and consumers want a knob that says "show me INFO and up." Adding a threshold dial is a small, self-contained pre-requisite for the larger LDD reshape parked in BACKLOG — and it rides cleanly on the `A2kitConfig` + provider-chain machinery we just landed.

## What Changes

- **NEW**: `A2kitConfig.ldd.level` field (default `info`), with values `trace | debug | info | warning | error`. Settable via env (`A2KIT_LDD__LEVEL=debug`), .env file, or App kwargs — same source precedence as the rest of `A2kitConfig` (env wins, per ADR 0022).
- **NEW**: a single-point filter in the LDD emission path that drops emissions below the configured threshold *before* sink fan-out. Implemented in `src/a2kit/packages/ldd/emission.py` at the entry of `log()`/`event()`/`report()` — checks `app.config.ldd.level` against the call-site level and short-circuits if below.
- **MODIFIED**: `event()` and `report()` gain an explicit `level` parameter (default `info`) so they participate in the filter. Today they are hardcoded `info` on the wire — keeping `info` as default preserves current behaviour for existing callers.
- **MODIFIED**: `debug()` shorthand now respects the threshold. Today every `debug(...)` call reaches sinks unconditionally; after this change, with the default `level=info`, debug emissions are dropped. Consumers wanting them flip `A2KIT_LDD__LEVEL=debug`.
- **BREAKING**: Default `ldd.level=info` silences existing `debug()` calls. Any consumer relying on debug-level emissions being visible must explicitly set `A2KIT_LDD__LEVEL=debug` (env), or pass `A2kitConfig(ldd=LddConfig(level="debug"))` to `App`.
- **Documentation**: README `## Configuration` table gains `A2KIT_LDD__LEVEL` row. AGENTS.md provider-chain block adds LDD as a worked example.

**Explicit non-goals (deferred to LDD reshape in BACKLOG):**
- No change to the operator/wire sink split.
- No promotion of operator sinks (stderr/OTel/file) to framework defaults.
- No rename of the LDD package or its primitives.
- No fusion of `event`/`log` into a single `emit()` primitive.
- No change to existing sink boolean kill-switches (they keep working as per-sink overrides, just stop being the only volume control).

## Capabilities

### New Capabilities

- `ldd-level-threshold`: Per-emission level + global threshold filter for LDD diagnostics; defines the level vocabulary, the source-of-truth knob in `A2kitConfig.ldd.level`, and the filter contract (drop before fan-out, never after).

### Modified Capabilities

- `runtime-config`: Adds the `LddConfig` sub-model and the `ldd: LddConfig` field on `A2kitConfig`. Same env-prefix and source-order rules as existing sub-configs.

## Impact

- **Code touched**: `src/a2kit/config.py` (add `LddConfig`), `src/a2kit/packages/ldd/emission.py` (add filter + extend `event()`/`report()` signatures), `src/a2kit/packages/ldd/__init__.py` (re-export `LddConfig` if needed by consumers).
- **Tests**: new `tests/ldd/test_level_threshold.py` covering default-drops-debug, env-overrides-default, explicit-level-on-event-respected, threshold-applied-before-fan-out, kwarg-loses-to-env (ADR 0022 worked example).
- **Consumers**: a2web's `event()` calls land at `info` (no change in visibility). a2sdlc and any code calling `debug()` directly become silent by default — owners decide whether to bump their emissions to `info` or instruct deployments to set `A2KIT_LDD__LEVEL=debug`.
- **Docs**: README config table, AGENTS.md provider-chain block, CHANGELOG `Breaking` entry, ADR 0022 cross-reference (worked example of the provider chain in action for a runtime knob).
- **Deferred**: ADR 0022 itself does not need an amendment; this change *applies* the model, it does not change it.
