## 1. Engine

- [x] 1.1 Add `debug: bool = False` top-level field to `A2kitConfig` in `src/a2kit/config.py`.
- [x] 1.2 In `App.__init__`: remove the `debug` kwarg. Source `self.debug = self.config.debug` after `self.config` is constructed.
- [x] 1.3 In `_raise_unexpected_kwargs`: add a `"debug"` branch with the migration hint (point at `A2KIT_DEBUG=true` env and `A2kitConfig(debug=True)`).

## 2. Tests

- [x] 2.1 Audit all `App(.*debug=True)` and `App(.*debug=False)` call sites under `tests/`.
- [x] 2.2 Rewrite each to use `A2kitConfig(debug=True)` via the `config=` kwarg (preferred, deterministic) or `monkeypatch.setenv("A2KIT_DEBUG", "true")` where env-driven coverage matters.
- [x] 2.3 Add explicit tests for the new behaviour:
  - `App(debug=True)` raises TypeError with migration hint.
  - `app.debug` proxies `app.config.debug`.
  - Env `A2KIT_DEBUG=true` wins over `A2kitConfig(debug=False)` kwarg.

## 3. Spec sync

- [x] 3.1 `core-composition`: validate the delta lands the new `debug` kwarg removal scenario + the env-beats-kwarg scenario.
- [x] 3.2 `operational-contracts`: scenarios that say `App(debug=True)` reworded to `app.config.debug == True`.
- [x] 3.3 `runtime-config`: `debug` field added with four scenarios (default, env-on, env-beats-kwarg, app.debug proxy).
- [x] 3.4 ADR 0017 surface table: `a2kit.App(name, *, debug=False)` reworded.
- [x] 3.5 ADR 0019: any debug citations updated (skim for collateral).

## 4. Docs

- [x] 4.1 README: add `## Configuration` section with precedence diagram (env > .env > kwarg > default), the `A2KIT_<SUBSYSTEM>__<KNOB>` convention, and `A2KIT_DEBUG` + `A2KIT_MCP__STRUCTURED_OUTPUT` worked examples. Link to ADR 0022.
- [x] 4.2 AGENTS.md: one paragraph under "Patterns" (or equivalent) pointing at ADR 0022 and stating "consumer beats code, no freeze hatch."
- [x] 4.3 ANTIPATTERNS.md: new entry "Hard-coding consumer concerns in App() construction" with the debug kwarg removal as the canonical example. Cite ADR 0022.
- [x] 4.4 OPERATIONAL_CONTRACTS.md: replace `App(debug=True)` citations with `A2kitConfig(debug=True)` / `A2KIT_DEBUG=true`.
- [x] 4.5 CHANGELOG.md: prepend a v0.X entry summarising the breaking change + the migration hint.

## 5. Gates

- [x] 5.1 Full test suite green (`uv run pytest --no-cov`).
- [x] 5.2 Ruff clean (`uv run ruff check src/ tests/`).
- [x] 5.3 Mirror lint clean.
- [x] 5.4 `openspec validate migrate-debug-to-config` passes.
- [x] 5.5 ADR INDEX regenerated.
