## 1. Verb-decorator footguns and dead surface (`src/a2kit/tool.py`)

- [x] 1.1 In `_build_annotation_kwargs`, raise `TypeError` when `idempotent=True` (or any non-default `idempotent` argument) is passed with `verb in {"read", "list"}`. Message names the kwarg, the verb, and suggests `@a2kit.write` for repeat-safe writes.
- [x] 1.2 In `_build_annotation_kwargs`, raise `TypeError` when an explicit `annotations=ToolAnnotations(...)` is passed alongside any of `idempotent`, `open_world`, `destructive`, `title`. Message names both `annotations` and the conflicting kwargs.
- [x] 1.3 Add a return-annotation check at the top of `list_()` decorator body: resolve `fn.__annotations__["return"]` (or via `typing.get_type_hints`); raise `TypeError` if `typing.get_origin(ret)` is not in `{list, tuple, set, frozenset}` or if `ret is None`. Emit `RuntimeWarning` if origin is `list`/`tuple`/etc. but no type parameter is present.
- [x] 1.4 Add `page_size` validation in `list_()`: raise `ValueError` when `page_size is not None and page_size <= 0`.
- [x] 1.5 Remove `name: str | None = None` parameter from the public signatures of `tool`, `read`, `write`, `list_` decorators. Add a private `_read_internal` helper module (or rename the existing internal call in `app.py:151`) that retains `name=` for the `_meta.health` registration; expose via internal-only path not in `a2kit.__getattr__`.
- [x] 1.6 Delete the public `tool()` function and remove `"tool"` from `_LAZY_ATTRS` in `src/a2kit/__init__.py`. Add a clear `AttributeError` message when consumers import `a2kit.tool`, suggesting `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`.
- [x] 1.7 Remove all references to `@tool` from internal tests and lint fixtures; switch lint fixtures to `@a2kit.write(destructive=False)` to exercise the same code paths.
- [x] 1.8 Update `tests/test_verb_annotations.py`:
  - flip the test asserting `idempotent=True` is accepted on `@read` to assert `TypeError` is raised (mirror the existing `destructive`-on-read test pattern)
  - flip `test_explicit_annotations_kwarg_wins` to assert `TypeError` on the mix instead
  - add a test that `@a2kit.list_("id")` decorating a `-> dict` function raises `TypeError`
  - add a test that `@a2kit.list_("id", page_size=0)` raises `ValueError`
  - add a test that `@a2kit.list_("id")` decorating `-> list[Task]` succeeds and stamps `selectable_fields`
  - add a test that `@a2kit.read(name="x")` raises `TypeError`
- [x] 1.9 Update `tests/test_health.py:123` to use the private `_read_internal` helper (or remove the test if it duplicates internal `_meta.health` coverage).
- [x] 1.10 Update `tests/packages/mcp/test_listview_e2e.py:31` to remove the `name="plain_things"` kwarg; rename the method if a custom tool name is needed.

## 2. Health probe: auto-enable + decouple from testing (`src/a2kit/app.py`, `src/a2kit/packages/cli/builder.py`, `src/a2kit/packages/testing/`, `src/a2kit/packages/health/`)

- [x] 2.1 In `App.health_check`, detect whether `_meta.health` is already installed; if not, call `self._install_health_tool()` (or the equivalent path used by `health_tool=True`) once. Make `_install_health_tool` idempotent so calling `App(health_tool=True)` + `@app.health_check` does not double-install.
- [x] 2.2 In `App.__init__`, when `health_tool=True` is passed but no checks are registered yet, still install eagerly (preserve back-compat). When `health_tool=False` (default), defer installation until first `@app.health_check` call.
- [x] 2.3 Add a test in `tests/test_health.py` verifying that constructing an app without `health_tool=True` and applying `@app.health_check` results in `_meta.health` appearing in `app.tools()`.
- [x] 2.4 Refactor `health_cmd` in `src/a2kit/packages/cli/builder.py:475` to NOT import `a2kit.packages.testing.client`. Replace the test-client invocation with a direct call to `a2kit.packages.health.run_checks(app)` wrapped in `asyncio.run(...)` inside the App's `lifespan_cm()`. Render the result as JSON to stdout; exit code = 0 on `status=="ok"`, non-zero otherwise.
- [x] 2.5 Verify by inspection that the new `health_cmd` path imports no symbol from `a2kit.packages.testing.*`.
- [x] 2.6 Add a smoke test under `tests/test_cold_start.py` (or a new `tests/test_cli_no_dev_deps.py`) that uses `subprocess` to create a tmp venv with only runtime deps installed (no `pytest`), installs the repo, runs `<app> health` against a tiny fixture App, and asserts exit code matches expectation. If full venv creation is too heavy for the test suite, fall back to: import `a2kit.packages.cli.builder`, invoke `health_cmd` programmatically with a stub app, and assert `"a2kit.packages.testing" not in sys.modules` afterwards.
- [x] 2.7 Guard `import pytest` in `src/a2kit/packages/testing/fixtures.py` behind `TYPE_CHECKING` (defense-in-depth — even with #2.4 decoupling, the testing package itself should not crash if pytest is absent at import time when only fixture *type hints* are used).

## 3. App.tools() collapse to ToolDescriptor (`src/a2kit/app.py`)

- [x] 3.1 Change `App.tools()` return type from `list[Callable[..., Any]]` to `list[ToolDescriptor]`. Update the implementation to return `list(self._descriptors)`.
- [x] 3.2 Delete `App.tool_descriptors()`. Replace its `__getattr__` machinery (or any internal references) so that calling `app.tool_descriptors()` raises a clear `AttributeError` naming `app.tools()` as the replacement.
- [x] 3.3 Audit `src/a2kit/` for internal call sites that called `app.tools()` expecting callables; update them to use `[d.fn for d in app.tools()]` or the underlying `_descriptors` list directly.
- [x] 3.4 Audit `src/a2kit/packages/` for the same; update.
- [x] 3.5 Update tests under `tests/` that compare `app.tools()` to callable lists; either change assertion to `[d.fn for d in app.tools()]` or to inspect descriptor fields.
- [x] 3.6 Update the `mcp-tool-descriptors` and `tool-descriptors` related test files to assert the new shape.

## 4. App.singleton method-only form (`src/a2kit/app.py`)

- [x] 4.1 In `App.singleton`, delete the decorator-form branch (the `if factory is None: return _decorator` block). When `factory is None`, treat `type_` as class-as-factory (like `provide`) — the container will introspect `type_.__init__` at resolve time.
- [x] 4.2 Ensure `App.singleton` always returns `self` for chaining.
- [x] 4.3 Update `tests/test_app_lifecycle_and_di.py:86` (the `@app.singleton(_State)` decorator-form test) to use the method-call form.
- [x] 4.4 Search for any other test or example using `@app.singleton(...)` decorator form; migrate to method form.

## 5. Drop stacked `@reports(T)` decorator (`src/a2kit/packages/mcp/reports.py`, `src/a2kit/packages/lint/`)

- [x] 5.1 Delete the `reports(...)` decorator factory from `src/a2kit/packages/mcp/reports.py`. Keep the `_compute_report_schema` helper (it's used by the `reports=` kwarg path).
- [x] 5.2 Update `A2K-LDD-REPORT-TYPE` lint rule in `src/a2kit/packages/lint/`: remove the "type defined inside a function" branch (no longer reachable since the kwarg form requires an importable type at the decoration site). Keep the "report() without declared type" branch.
- [x] 5.3 Search the codebase for any remaining import `from a2kit.packages.mcp.reports import reports`; replace with the verb-decorator `reports=` kwarg.
- [x] 5.4 Update tests that exercised the stacked form to use the kwarg form.

## 6. AmbientContextMissing message split (`src/a2kit/exceptions.py` or wherever `_require_ambient_state` lives)

- [x] 6.1 Locate `_require_ambient_state` (likely in `src/a2kit/packages/ldd/` or `src/a2kit/ldd.py`). Split the raise into two branches:
  - if `state` is None → existing "called outside an active tool dispatch" message
  - if `state` is not None but `state.ctx is None` → new "tool body did not declare `ctx: a2kit.ToolContext` as a parameter" message
- [x] 6.2 Both branches raise the same `AmbientContextMissing` class.
- [x] 6.3 Add tests covering both messages (Mode A and Mode B per the spec).

## 7. README rescue and drift CI test

- [x] 7.1 Walk `README.md` and remove every reference to `@app.on_startup` and `@app.on_shutdown`. Replace each example with the canonical `App(lifespan=async_cm)` pattern.
- [x] 7.2 Remove references to `Router.on_startup` / `Router.on_shutdown` methods.
- [x] 7.3 Replace `Surface` Flag-enum mentions with `Visibility = Literal["hidden", "cli", "all"]`. Document the three values.
- [x] 7.4 Remove all `@a2kit.tool` mentions; show `@a2kit.read` / `@a2kit.write` instead.
- [x] 7.5 Remove `name=` and `tags=` from all verb-decorator examples.
- [x] 7.6 Replace `app.tool_descriptors()` references with `app.tools()`.
- [x] 7.7 Update connection-wiring example: ensure `install_connections(app, ConnT)` is shown as a single call (no redundant `add_cli(connections_cli(ConnT))` if `install_connections` already does it).
- [x] 7.8 Update `app.singleton` examples to method-call form only.
- [x] 7.9 Spell out the `LDD` acronym ("logging, data, diagnostics") at first mention.
- [x] 7.10 Update `src/a2kit/ldd.py` module docstring to spell out the acronym.
- [x] 7.11 Add a short note in README about the `list_` trailing-underscore convention (avoids shadowing built-in `list`).
- [x] 7.12 Document the default connection-store path (read from `src/a2kit/packages/connections/config.py` for the actual path).
- [x] 7.13 Fix `Router.slug` docstring in `src/a2kit/routers.py` to accurately describe auto-derivation behavior (currently denies it).
- [x] 7.14 Create `tests/test_readme_symbol_drift.py`:
  - Read `README.md`.
  - Extract symbol references from fenced code blocks and backtick spans matching patterns: `a2kit.X`, `@a2kit.X`, `a2kit.<submodule>.X`, `App.X` / `app.X`, `Router.X`, `@app.X`.
  - For each, attempt resolution via `hasattr(a2kit, X)` / `importlib.import_module(...)` / `hasattr(App, X)` / `hasattr(Router, X)`.
  - Collect failures into a single assertion that names each missing symbol with its README line number.
- [x] 7.15 Run the new drift test locally; iterate on README fixes until green.
- [x] 7.16 Wire the drift test into `make lint` (add to the `Makefile` lint target invocation list).

## 8. CHANGELOG.md and migration message audit

- [x] 8.1 Add a v0.33 entry to `CHANGELOG.md` following the v0.31/v0.32 format. Cover, in order: bugfix (`<app> health` pytest), breaking changes (each footgun raise, each dropped surface), and the docs-code-parity gate.
- [x] 8.2 For each removed symbol (`@a2kit.tool`, `name=`, `tags=`, `tool_descriptors()`, stacked `@reports`, `@app.singleton(T)` decorator form), verify the error message at the failure point names the symbol AND points at the replacement. Add the message text to the CHANGELOG entry.
- [x] 8.3 Cross-reference the migration steps in `proposal.md → Migration Plan` with what's actually shipped; reconcile any discrepancy.

## 9. Verification

- [x] 9.1 Run `make lint` — all gates pass (ruff, ty, openspec validate, README drift test).
- [x] 9.2 Run the full test suite — all green.
- [x] 9.3 Verify on a fresh venv (no dev deps): install a tiny app, run `<app> health`, confirm no `ModuleNotFoundError`.
- [x] 9.4 Manual smoke: import `a2kit`, list public symbols (`dir(a2kit)`), confirm `tool` is absent and `App`, `Router`, `read`, `write`, `list_`, `ToolContext`, `HealthResult`, `A2KitError`, `run` are present.
- [x] 9.5 Spot-check a2web on the new pin: bump a2web's `a2kit` git tag to `v0.33`-equivalent, run a2web's test suite, confirm no breakage.
