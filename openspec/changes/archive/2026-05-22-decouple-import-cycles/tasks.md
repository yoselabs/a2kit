## 1. Leaf context package (breaks `mcp → cli`)

- [x] 1.1 Create `src/a2kit/packages/context/__init__.py`
- [x] 1.2 Move `StderrToolContext` from `packages/cli/context.py` into
      `packages/context/`
- [x] 1.3 Audit `packages/cli/context.py` for other types imported by
      non-`cli` packages (`packages/testing` deep-imports it too); the
      whole module was transport-neutral (`MCPOnlyError`,
      `_StubResourceResult`, `StderrToolContext`) — all moved
- [x] 1.4 Add `packages/context/` to the `A2K-IMPORT-DISCIPLINE`
      `_FASTMCP_ALLOWLIST` — `StderrToolContext` mirrors
      `fastmcp.Context`'s elicitation result types (lazy import, same
      as the old `cli/context.py` allowlist entry)
- [x] 1.5 `packages/cli/context.py`: tombstone module — `__getattr__`
      raises a migration hint on the old names
- [x] 1.6 Update `packages/mcp/_wrappers.py` and `packages/testing` to
      import from `a2kit.packages.context`
- [x] 1.7 `packages/context` imports no transport package (regression
      test `test_context_package_is_low_level`); its only
      `a2kit.packages.*` edge is the lazy `ldd` import

## 2. Relocate `run_code` to the CLI (breaks `codemode → mcp`)

- [x] 2.1 `run_code` moved into `packages/cli/_serve.py` (the lazily
      loaded `serve`/`code` module), `build_mcp_server` import stays
      function-local so it is off the cold-start path
- [x] 2.2 Removed `run_code` and the `mcp.server` import from
      `codemode/__init__.py`; dropped `run_code` from `__all__`
- [x] 2.3 `cli/_serve.py::code_cmd` calls the relocated module-level
      `run_code` directly
- [x] 2.4 `codemode/__init__.py` `__getattr__` tombstone raises a
      migration hint on the old `run_code` path
- [x] 2.5 Fixed the stale `run_code` docstring (the MCP `execute` tool
      builds itself independently; the two do not share code)

## 3. Retype `run_checks` (breaks `app ↔ health`)

- [x] 3.1 `run_checks(registry, resolver, *, version="unknown")` —
      resolves check DI deps via the `Resolver`; new exported
      `app_version` helper owns the version-string coercion
- [x] 3.2 `app.py::_install_health_tool` passes the App's registry +
      resolver + `app_version(app)` into `run_checks`
- [x] 3.3 Removed the `TYPE_CHECKING` import of `App` from
      `packages/health/__init__.py`; health imports no `a2kit.app`
- [x] 3.4 `app.py`'s `health` imports stay deferred — now for
      cold-start hygiene only (keep bare `import a2kit` light), no
      longer for cycle reasons

## 4. Verify the testing-shim cycle is absent

- [x] 4.1 Confirmed `packages/testing/fixtures.py` imports nothing from
      the core `a2kit.testing` shim — the flagged line is a docstring
      example, not an import statement
- [x] 4.2 Confirmed `packages/testing/null_context.py` likewise imports
      nothing from `a2kit.testing`
- [x] 4.3 Regression test: no `packages/testing` module imports
      `a2kit.testing` (`test_packages_testing_does_not_import_core_shim`)

## 5. Type the MCP dispatch wrappers

- [x] 5.1 Module-level imports of `App` (`a2kit.app`) and `Router`
      (`a2kit.routers`) in `_wrappers.py` — proving the cycle is gone
- [x] 5.2 `app: Any` → `app: App`, `router: Any | None` →
      `router: Router | None` on the `_wrap_with_*` functions
- [x] 5.3 `make lint` / ty: zero new errors in `src/`

## 6. Tests (BDD-first)

- [x] 6.1 `test_mcp_server_does_not_import_cli` /
      `test_wrappers_does_not_import_cli`
- [x] 6.2 `test_codemode_does_not_import_mcp_server`
- [x] 6.3 `test_health_does_not_import_app`
- [x] 6.4 `test_packages_testing_does_not_import_core_shim`
- [x] 6.5 old `run_code` / `StderrToolContext` paths raise migration
      hints (`test_import_acyclicity.py`, `packages/cli/test_context.py`)
- [x] 6.6 `test_run_checks_aggregates_through_resolver` +
      `test_run_checks_version_is_caller_supplied`
- [x] 6.7 cold-start benchmark runs and is unchanged (`import a2kit`
      ~27ms, fastmcp-free); `bench/cli_cold_start.py` itself was
      pre-existingly stale on removed APIs and was refreshed

## 7. Wrap-up

- [x] 7.1 CHANGELOG `Unreleased`: migration rows for `run_code`,
      `run_checks`, `StderrToolContext`
- [x] 7.2 ANTIPATTERNS.md #27: function-local / `TYPE_CHECKING` imports
      used to dodge a package cycle
- [x] 7.3 `make lint`, `make test` green (1025 passed, 90.44% cov);
      `openspec validate decouple-import-cycles --strict`
- [x] 7.4 `openspec archive decouple-import-cycles`
