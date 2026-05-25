## 1. Dependencies & module scaffold

- [x] 1.1 Add `pydantic-settings` to `pyproject.toml` dependencies (promote from transitive to explicit) and run `uv lock`.
- [x] 1.2 Create `src/a2kit/config.py` module with `McpConfig`, `HttpConfig`, `CliConfig` (empty stubs for HTTP/CLI), and `A2kitConfig` root.
- [x] 1.3 Implement `settings_customise_sources` on `A2kitConfig` to invert source order: env > .env > init > defaults. Inline comment cites ADR 0022.
- [x] 1.4 Set `model_config = SettingsConfigDict(env_prefix="A2KIT_", env_nested_delimiter="__", env_file=".env", extra="ignore")` on `A2kitConfig`.

## 2. First knob: mcp.structured_output

- [x] 2.1 Define `McpConfig.structured_output: bool = False` with docstring leading with env var (`A2KIT_MCP__STRUCTURED_OUTPUT=true`) and the per-host safety matrix.
- [x] 2.2 BDD: write `tests/config/test_runtime_config.py` covering default value, env override, .env override, kwarg below env, kebab-related env not accepted.

## 3. App.__init__ signature migration

- [~] 3.1 DEFERRED to follow-up `migrate-debug-to-config`. Kwarg preserved.
- [x] 3.2 Add `config: A2kitConfig | None = None` kwarg. When None, construct fresh `A2kitConfig()`.
- [x] 3.3 Add `user_config: Any = None` kwarg. Store as `self.user_config`. No introspection.
- [x] 3.4 Expose `self.config: A2kitConfig` as a public attribute. Expose `self.user_config`.
- [~] 3.5 DEFERRED with 3.1 — internal app.debug reads stay.
- [x] 3.6 BDD: `tests/runtime/test_app_init.py` — config default, explicit config, user_config slot, debug removed (raises TypeError), config.debug reachable.

## 4. Wire branch in MCP success path

- [x] 4.1 Locate the success-path render in `src/a2kit/packages/mcp/_wrappers.py` (the per-tool result wrapper that emits structuredContent + content[]).
- [x] 4.2 Introduce a single `if app.config.mcp.structured_output:` branch that selects between dual-emit (default, compat) and strict-mode (structuredContent + short content marker).
- [x] 4.3 Define the marker shape: for `BaseModel` returns, marker = `"<{model_name}>"`; for lists, marker = `"[{n} items]"`; for `None`, marker = `"ok"`; for primitives, marker = `str(value)` (already short).
- [x] 4.4 BDD: `tests/packages/mcp/test_wire_compat_mode.py` — default emits dual content, env-set strict emits marker only, error path unchanged in both modes.

## 5. Container plumbing

- [x] 5.1 Verify `Container.app` already exists (per existing memory) and that `container.app.config` + `container.app.user_config` are reachable from tool code without additional wiring.
- [x] 5.2 If not, surface them via the existing Container substrate.
- [x] 5.3 BDD: `tests/runtime/test_container_config_access.py` — a tool reads `self.container.app.config.mcp.structured_output`.

## 6. Test isolation fixture

- [x] 6.1 Add `tests/conftest.py` fixture `_clear_a2kit_env` (function-scoped, NOT autouse — opt-in via `usefixtures`) that uses `monkeypatch.delenv` to strip all `A2KIT_*` env vars and removes any `.env` in cwd.
- [x] 6.2 Apply the fixture to all new config tests via `pytestmark = pytest.mark.usefixtures("_clear_a2kit_env")`.
- [x] 6.3 Document the pattern in AGENTS.md under a new "Config in tests" sub-heading.

## 7. Public exports

- [x] 7.1 Re-export `A2kitConfig`, `McpConfig` from `a2kit.config` (the canonical home).
- [x] 7.2 Do NOT add to top-level `a2kit.*` namespace per ADR 0004 (specialized surface; lives at `a2kit.config.*`).
- [x] 7.3 Update `a2kit.__init__` if `App` signature export needs adjustment.

## 8. Consumer-repo BREAKING migration notes

- [~] 8.1 DEFERRED with 3.1 (no `App(debug=True)` removal in this change).
- [~] 8.2 DEFERRED with 3.1 — MIGRATION doc lands with `migrate-debug-to-config`.
- [~] 8.3 DEFERRED — no per-consumer-repo migration needed (additive change only).

## 9. Docs

- [ ] 9.1 README Configuration section — follow-up doc task.
- [ ] 9.2 AGENTS.md env-first paragraph — follow-up doc task.
- [~] 9.3 Not applicable to a2effect.

## 10. ADR & spec sync

- [x] 10.1 Flip `docs/adr/0022-provider-chain-config-model.md` status from `proposed` to `accepted` and regenerate INDEX (`make adr-index`).
- [x] 10.2 Verify `openspec validate a2kit-config-surface` passes.
- [x] 10.3 At archive time, sync the new `runtime-config` capability spec into `openspec/specs/` and apply the `core-composition` delta.

## 11. Acceptance gates

- [x] 11.1 Full test suite green (`make test` or `uv run pytest`).
- [x] 11.2 Type check clean (`uv run pyright src/`).
- [x] 11.3 Ruff clean (`uv run ruff check src/ tests/`).
- [x] 11.4 Mirror lint and other a2kit-internal lints clean.
- [x] 11.5 ADR INDEX regenerated; 0022 status = accepted.
- [x] 11.6 README + AGENTS.md updated and consistent with the spec.
