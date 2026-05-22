## 1. Collapse to one `App` type

- [x] 1.1 In `src/a2kit/app.py`, merge `AppBuilder` and `App` into a
      single public `App` class: the public constructor (`App(name, *,
      debug=False)`) builds the mutable composition object; it carries
      the composition verbs (`add_router`, `add_cli`,
      `add_mcp_middleware`, `provide`, `health_check`), the runtime
      accessors (`tools`, `routers`, `container`, `_resolver`,
      `cli_extras`, `mcp_middlewares`, `dispatch_hook`,
      `has_default_dispatch_hook`, `set_ldd`, LDD props), and the
      async-CM protocol
- [x] 1.2 Add a private `_sealed: bool` flag and a private
      `_seal()` method (validate the provider graph + lock the
      container via `Container.seal()`); `_seal()` is idempotent
- [x] 1.3 Composition verbs raise `TypeError` (action-oriented hint)
      when called on a sealed `App`; non-verb attribute misses stay
      `AttributeError`
- [x] 1.4 Remove the `AppBuilder` class, the public `build()` method,
      the `App.__init__`-raises tombstone, the `_build_from`
      classmethod, and the `__getattr__` composition-verb interception
- [x] 1.5 Tests (BDD-first) in `tests/test_app.py`: `App` is
      constructed directly; verbs chain and return the `App`; a sealed
      `App` rejects composition verbs

## 2. Finishers seal internally

- [x] 2.1 `a2kit.run(app)` calls `app._seal()` before building the CLI
- [x] 2.2 `a2kit.packages.mcp.build_mcp_server(app)` calls `app._seal()`
      before building the FastMCP server
- [x] 2.3 `a2kit.testing.client(app)` / `TestClient.__aenter__` calls
      `app._seal()` before constructing the in-process transport
- [x] 2.4 Tests: a finisher rejects a bad provider graph; one `App`
      passed to two finishers raises no "spent"/"sealed" error

## 3. Surface + entry-point updates

- [x] 3.1 `src/a2kit/__init__.py`: remove `AppBuilder` from
      `_LAZY_ATTRS` and `__all__`; keep `App`
- [x] 3.2 `src/a2kit/packages/connections/__init__.py`: retype
      `install_connections(app: App, ...)` (was `AppBuilder`)
- [x] 3.3 `src/a2kit/packages/testing/fixtures.py`: rename the
      `builder` fixture back to `app`; yield a fresh `a2kit.App("test")`;
      update the `a2kit.packages.testing` and `a2kit.testing`
      re-export modules and their `__all__`
- [x] 3.4 `src/a2kit/packages/testing/client.py`: update the
      `TestClient.override` removed-name migration hint to name `App`
      (not `AppBuilder`)

## 4. Migrate consumers in-repo

- [x] 4.1 Migrate `examples/` — every `a2kit.AppBuilder(...).build()`
      and `.build()` chain becomes `a2kit.App(...)`
- [x] 4.2 Migrate `tests/` and `examples/**/tests/` composition sites,
      including the `app` fixture consumers and
      `tests/test_app.py` / `tests/test_testing_di_override.py`

## 5. Decision log + docs

- [x] 5.1 Write a new ADR recording the narrowed framework⇄consumer
      contract (one public `App`, internal sealed runtime, finishers
      seal); set its `supersedes` to `["0016"]`
- [x] 5.2 Set ADR 0016's `superseded_by` to the new ADR id; run
      `make adr-index`; `make adr-check` green
- [x] 5.3 Update README, AGENTS.md, and `docs/patterns/test-overrides.md`
      to the one-`App` form (no `AppBuilder`, no `build()`)
- [x] 5.4 CHANGELOG `Unreleased`: migration row for
      `AppBuilder(...).build()` → `App(...)`

## 6. Wrap-up

- [x] 6.1 `make check` (lint + test), `make example-smoke`,
      `make markdown-lint`, `make adr-check` all green
- [x] 6.2 `openspec validate internalize-app-runtime --strict`
- [x] 6.3 `openspec archive internalize-app-runtime`
