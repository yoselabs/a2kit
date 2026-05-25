## MODIFIED Requirements

### Requirement: The threshold is read once per dispatch and stamped onto ambient state

The dispatch site (the LDD-state stage of `fold_pipeline`) SHALL obtain `LddConfig` via constructor injection at pipeline build time (or via a one-shot read of `spec.app.config.ldd` when the stage is built without explicit injection, e.g. the default module-level pipeline). The captured `LddConfig.level` SHALL be converted to its numeric rank via `LDD_LEVEL_RANK` once at wrap time and stamped onto the per-call ambient state object as `level_threshold: int`. Emission primitives SHALL read the threshold from the ambient state, not by re-resolving the App or its config on each call. The previous per-call attribute walk on `spec.app.config.ldd.level` is retired; `LddConfig` is treated as immutable for the lifetime of the runtime.

#### Scenario: Stage captures LddConfig at wrap time

- **GIVEN** a pipeline being constructed for an `App` whose `config.ldd.level` is `"warn"`
- **WHEN** `LddStateStage` wraps a tool
- **THEN** the captured `LddConfig.level` is `"warn"`
- **AND** the captured threshold is stamped onto every subsequent ambient state for that tool

#### Scenario: per-call state carries the threshold rank

- **WHEN** a tool dispatch is in progress with `app.config.ldd.level="debug"`
- **THEN** the ambient state's `level_threshold` is `20`

#### Scenario: Test rebinds LddConfig before build

- **GIVEN** a fresh `App` and a test that wants `LddConfig(level="debug")`
- **WHEN** the test calls `app.provide(LddConfig, lambda: LddConfig(level="debug"))` before building the runtime
- **THEN** the resulting pipeline's `LddStateStage` is constructed with the test-supplied `LddConfig`
- **AND** `ldd.debug(...)` emissions are not dropped
