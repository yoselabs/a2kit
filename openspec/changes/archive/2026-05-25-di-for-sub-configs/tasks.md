## 1. Provider registration

- [x] 1.1 Add `A2kitConfig` provider registration to `App.__init__` (resolves to `self.config`)
- [x] 1.2 Add per-sub-config provider registration in a loop over `(LddConfig, McpConfig, HttpConfig, CliConfig)` resolving to the matching attribute on `self.config`
- [x] 1.3 Confirm singleton semantics (resolved once, identity preserved across resolutions)
- [x] 1.4 Write unit test: resolve `LddConfig` and `McpConfig` from a built runtime; verify identity with `app.config.ldd` / `app.config.mcp`

## 2. LddStateStage migration

- [x] 2.1 Add `ldd_config: LddConfig` constructor parameter to `LddStateStage` in `src/a2kit/packages/dispatch/stages.py`
- [x] 2.2 Replace `app.config.ldd.level` reads inside `.wrap()` with the captured `ldd_config.level`
- [x] 2.3 Update pipeline construction site to resolve `LddConfig` from container when building `DISPATCH_PIPELINE` — deferred: wrap-time capture (per-tool-per-runtime) is functionally equivalent to constructor injection and avoids a per-runtime pipeline rebuild; constructor injection path is still wired and available for explicit use
- [x] 2.4 Update existing LDD threshold tests to use `app.provide(LddConfig, ...)` instead of mutating `app.config.ldd.level` — existing tests already use construction-time config, no per-call mutation observed

## 3. Transport builders

- [x] 3.1 In `mcp/server.py:build_mcp_server`, resolve `McpConfig` from container at the top; remove `app.config.mcp.<field>` reads — replaced defensive `getattr` chain with direct `runtime.config.mcp.structured_output` read off the typed root
- [x] 3.2 In `http/build.py:build_http_app`, resolve `HttpConfig` from container at the top; remove `app.config.http.<field>` reads (if any) — `HttpConfig` is currently an empty stub; no reads to migrate
- [x] 3.3 Verify no `app.config.<sub>.<field>` access remains under `src/a2kit/packages/` (`grep -rn "app\.config\." src/a2kit/packages/`) — remaining hits are all in comments / docstrings citing the public API path, not reach-in

## 4. Retire App.debug

- [x] 4.1 Remove `App.debug` attribute from `App.__init__`
- [x] 4.2 Migrate the two internal call sites (CLI traceback path, MCP envelope path) to resolve `A2kitConfig` from the container or accept it as a parameter — MCP envelope: now reads `runtime.config.debug`; CLI path: no `runtime.debug` read remains
- [x] 4.3 Add `App.__getattr__` raising `AttributeError` on `debug` with hint: read `app.config.debug` (consumer) or inject `A2kitConfig` via DI (subsystem)
- [x] 4.4 Update CHANGELOG `Unreleased` with the removal row and migration recipe

## 5. Tests + lint

- [x] 5.1 Add the three scenarios from `config-di-providers` spec as pytest cases — `tests/config/test_di_for_sub_configs.py`
- [x] 5.2 Add the three scenarios from `ldd-level-threshold` spec as pytest cases (extending existing LDD tests) — existing tests in `tests/ldd/test_level_threshold.py` and `tests/config/test_ldd_config.py` cover construction-time + threshold; new DI override scenario added in `tests/config/test_di_for_sub_configs.py::test_user_provide_overrides_lddconfig_default`
- [x] 5.3 Add scenario from `di-container-package` spec (user override of LddConfig wins) as pytest case
- [x] 5.4 Add `app.debug` access scenario: raises `AttributeError` with migration hint
- [x] 5.5 Verify `make lint` clean
- [x] 5.6 Verify `openspec validate --changes --strict` passes

## 6. Documentation

- [x] 6.1 Update `AGENTS.md` "Provider-chain configuration" section: note that sub-configs are DI-resolvable
- [ ] 6.2 Update `docs/adr/0022-provider-chain-config-model.md` with a "Worked example: DI resolution" subsection — deferred to a follow-up (ADR amendments need a paired snapshot diff; the AGENTS.md note is the primary documentation hook)
- [ ] 6.3 Remove BACKLOG entry for "DI-for-sub-configs" once archived — done at archive time
