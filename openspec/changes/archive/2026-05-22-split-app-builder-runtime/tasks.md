## 1. AppBuilder

- [ ] 1.1 Define `AppBuilder` in `src/a2kit/app.py` holding the mutable
      state (`_routers`, `_descriptors`, `_cli_extras`,
      `_mcp_middlewares`, provider registrations, health registry)
- [ ] 1.2 Move `add_router`, `add_cli`, `add_mcp_middleware`,
      `provide`, `health_check` onto `AppBuilder`
- [ ] 1.3 Implement `AppBuilder.build() -> App`: construct the
      `Container`, validate the provider graph, auto-install
      `_meta.health` if checks were registered, return the sealed `App`
- [ ] 1.4 Tests (BDD-first): `build()` returns an `App`; verbs chain
      and return `AppBuilder`

## 2. Sealed App

- [ ] 2.1 Reduce `App` to the runtime surface: `tools()`, `routers()`,
      `container()`, `_resolver`, async-CM `__aenter__`/`__aexit__`,
      LDD kill-switch, dispatch-hook accessor
- [ ] 2.2 `App` has no composition verbs and no `provide`
- [ ] 2.3 Test: an `App` instance exposes no mutating method

## 3. Loud-crash migration hints

- [ ] 3.1 `a2kit.App("name", ...)` constructed directly raises
      `TypeError` naming `AppBuilder`
- [ ] 3.2 Calling a composition verb on a built `App` raises
      `TypeError` with the `AppBuilder` migration recipe
      (`__getattr__` interception per AGENTS.md)
- [ ] 3.3 Tests: each removed-from-`App` surface raises with a hint

## 4. Replace the test-override seam with re-build

- [ ] 4.1 Delete `_override`, `_snapshot`, `_restore`, and
      `_ContainerSnapshot` from `packages/di/container.py`
- [ ] 4.2 Delete `_test_override_owner` from `App` / `AppBuilder`
- [ ] 4.3 Remove `TestClient.override()` and `_override_snapshot`;
      raise a migration hint on the old `override()` name pointing to
      "build a fresh App from an AppBuilder with the fake `provide`d"
- [ ] 4.4 Migrate `packages/testing` fixtures + `TestClient` wiring to
      accept an `AppBuilder` (or a build callable) so each test gets a
      freshly-built `App`
- [ ] 4.5 Reconcile ADR 0006: its Y-statement now matches the code —
      record (new ADR, or amendment per the append-only policy) that
      the snapshot/restore machinery was removed in favor of re-build
- [ ] 4.6 Tests: a fake `provide()`d on the builder wins last-write;
      no post-seal override path remains

## 5. Update entry points

- [ ] 5.1 `a2kit.run(...)` accepts the sealed `App`
- [ ] 5.2 `build_mcp_server(...)` accepts the sealed `App`
- [ ] 5.3 `a2kit/__init__.py` `_LAZY_ATTRS` + `__all__`: add
      `AppBuilder`

## 6. Migrate consumers in-repo

- [ ] 6.1 Migrate `examples/` (tracker, health_demo, mcp_google_auth,
      and the rest) to `AppBuilder(...).build()`
- [ ] 6.2 Migrate `tests/` composition sites, including any test that
      used `TestClient.override()`

## 7. Wrap-up

- [ ] 7.1 README + AGENTS.md: update the composition example to the
      builder form; document the re-build test-override pattern
- [ ] 7.2 CHANGELOG `Unreleased`: migration rows for
      `App(...)` → `AppBuilder(...).build()` and the removed
      `TestClient.override()`
- [ ] 7.3 BACKLOG.md: park Thread E (generalize `add_mcp_middleware`
      into a transport-neutral extension registry) with trigger
      "a third transport adapter is added" (see design D5)
- [ ] 7.4 `make lint`, `make test`, `make e2e` green;
      `openspec validate split-app-builder-runtime --strict`
- [ ] 7.5 `openspec archive split-app-builder-runtime`
