# Implementation Tasks

## 1. BDD tests first (lock the contract)

- [x] 1.1. Add `tests/ldd/test_level_threshold.py` covering: default drops debug, env beats kwarg, info passes under info, trace lets everything through, error drops below, `events_enabled=False` overrides threshold, invalid level raises, `event()` / `report()` respect explicit level, ranks exported and ordered.
- [x] 1.2. Add `tests/config/test_ldd_config.py` covering: default `level="info"`, env `A2KIT_LDD__LEVEL=debug` wins, kwarg loses to env, invalid value raises ValidationError.
- [x] 1.3. Run the new tests and confirm RED (no implementation yet).

## 2. Config sub-model

- [x] 2.1. Add `LddConfig(BaseModel)` to `src/a2kit/config.py` with `level: Literal["trace","debug","info","warning","error"] = "info"`.
- [x] 2.2. Add `ldd: LddConfig = LddConfig()` field to `A2kitConfig`.
- [x] 2.3. Export `LddConfig` from `a2kit.config` `__all__`.

## 3. Level vocabulary + rank constants

- [x] 3.1. Add `LddLevel = Literal["trace","debug","info","warning","error"]` type alias in `src/a2kit/packages/ldd/__init__.py` (or a small `levels.py` sibling).
- [x] 3.2. Add `LDD_LEVEL_RANK: dict[LddLevel, int] = {"trace": 10, "debug": 20, "info": 30, "warning": 40, "error": 50}` and export.

## 4. Ambient-state threshold plumbing

- [x] 4.1. Add `level_threshold: int` to the per-call state in `src/a2kit/packages/ldd/ambient.py` (next to `events_enabled`, `sinks`, `tool_name`).
- [x] 4.2. Update `ldd_state_for_call` (or whichever stage binds it) to read `app.config.ldd.level` and stamp `LDD_LEVEL_RANK[level]` onto the state at dispatch entry.

## 5. Primitive-side filter

- [x] 5.1. In `src/a2kit/packages/ldd/emission.py`, after `_require_ambient_state(...)` and the `events_enabled` short-circuit, add a level-rank check: if `LDD_LEVEL_RANK[level] < state.level_threshold` return immediately. Apply uniformly in `log()`, `event()`, `report()`.
- [x] 5.2. Extend `event(name, *, level: LddLevel = "info", **fields)` and `report(instance, *, level: LddLevel = "info")` signatures.
- [x] 5.3. Confirm shorthand primitives (`debug`/`info`/`warning`/`error`) pass their bound level through `log()` so the same filter applies.

## 6. Make tests pass

- [x] 6.1. Run `tests/ldd/test_level_threshold.py` and `tests/config/test_ldd_config.py` — confirm GREEN.
- [x] 6.2. Run full suite: `make test` (or `uv run pytest`). Fix any regressions in existing LDD tests where `debug()` calls now silently drop.

## 7. Lint, drift, layers

- [x] 7.1. `make lint` — pymarkdown, ruff, mirror-lint, layer-manifest, component-map. Add `LddConfig` to component-map if needed.
- [x] 7.2. Run `tests/test_spec_symbol_drift.py` and `tests/test_readme_symbol_drift.py`. Update allowlists or README symbols if drift is reported.

## 8. Docs

- [x] 8.1. README `## Configuration` table: add `A2KIT_LDD__LEVEL` row with default `info` and the allowed values.
- [x] 8.2. AGENTS.md provider-chain block: add an LDD bullet under "worked examples" pointing to this spec.
- [x] 8.3. CHANGELOG `Unreleased`: add `### Breaking` entry — "Default `A2KIT_LDD__LEVEL=info` drops sub-info LDD emissions (previously: all emissions reached sinks). Set `A2KIT_LDD__LEVEL=debug` to restore."
- [x] 8.4. CHANGELOG `Unreleased`: add `### Added` entry — `A2kitConfig.ldd.level` knob, `trace` level, `LDD_LEVEL_RANK` export, `event()` / `report()` `level` parameter.

## 9. Final gate

- [x] 9.1. `make lint && make test` — both green.
- [x] 9.2. Commit on `main` (solo repo, no PR).
- [x] 9.3. Run `/opsx:archive ldd-log-level`.
