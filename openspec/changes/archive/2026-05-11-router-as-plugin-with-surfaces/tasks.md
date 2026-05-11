## 0. Prerequisites

- [x] 0.1 Baseline green: 658 tests passing, `make lint` 0 findings, `uv run ty check src/` clean.
- [x] 0.2 Baseline test count: 658 (was 665 in test-quality-via-mutmut tasks.md §3.6; minor drift from later commits).
- [x] 0.3 Mirror discipline active — A2K-TEST-MIRROR rule runs in `make lint` and is currently 0-findings; new files in this change MUST have mirror tests.

## 1. Surface flag — core type + decorator kwarg

- [x] 1.1 `Surface` exposed on top-level `a2kit` namespace via lazy attrs in `__init__.py`.
- [x] 1.2 Implementation in `src/a2kit/surface.py` (A2K-CORE-CLEAN-safe at root; all existing peers like `routers.py`, `tool.py` live there). 34 LOC including docstring.
- [x] 1.3 Extended `tool`, `read`, `write`, `list_` decorators with `surfaces: Surface = Surface.ALL`; stored under `SURFACE_META_KEY` in `meta.extra` via `_stamp`.
- [x] 1.4 `tests/test_surface.py` — 8 tests covering Flag arithmetic, default, membership, all four decorators.
- [x] 1.5 Cold-start: 15.6ms (well under budget).

## 2. Transport mounters filter by Surface

- [x] 2.1 MCP server filters out tools missing `Surface.MCP` before `server.add_tool`.
- [x] 2.2 CLI `_router_group` filters out tools missing `Surface.CLI` before `group.add_command`.
- [x] 2.3 `tests/test_surface_filtering.py` covers CLI-only invisible-to-MCP and MCP-only invisible-to-CLI.
- [x] 2.4 `Surface.ALL` default verified visible on both transports.

## 3. Router grows providers + lifecycle

- [x] 3.1 `Router` grew `providers: tuple[Any, ...] = ()` class attribute. Subclasses override; entries may be `type` or `(type, factory)` tuple.
- [x] 3.2 Lifecycle methods (`on_startup`/`on_shutdown`) discovered via `type(router).__dict__` lookup in `add_router` — only subclass-defined methods fire, no base-class shadows.
- [x] 3.3 `App.add_router` calls `self.provide(...)` per entry and bridges router lifecycle methods to App lifecycle handlers.
- [x] 3.4 `tests/test_routers.py` covers: providers installed (class + tuple form), lifecycle hooks fire on startup/shutdown, plain Router unchanged.
- [x] 3.5 `make lint` clean post-phase — no new A2K-CORE-CLEAN findings.

## 4. `connections` factory + deprecation shim

- [x] 4.1 Added `src/a2kit/packages/connections/router.py` with `connections(*conn_types)` returning a Router whose `install(self, app)` calls `install_connection_providers` (the proper resolver-chain installer). Tools still ship as Click group; rewriting connection subcommands into a2kit tool methods is a separate follow-up.
- [x] 4.2 Re-exported `connections` from `a2kit.packages.connections.__init__`.
- [x] 4.3 Deprecation warning moved to the actual smell site — `App.add_cli` emits `DeprecationWarning` when the `_a2kit_connections_types` marker is present, pointing to the new two-call pattern. `connections_cli` itself unchanged.
- [x] 4.4 `tests/packages/connections/test_router.py` — 4 tests covering factory shape, provider installation, deprecation emission, and clean canonical path.
- [x] 4.5 Deprecation test covered above; `examples/tracker/server.py` updated to the canonical two-call form so the example no longer ships the smell.

## 5. `A2K-SURFACE-EXPLICIT` lint rule

- [x] 5.1 Created `src/a2kit/packages/lint/rules/surface.py` with `_CREDENTIAL_NAME_SUBSTRINGS` dictionary; each entry has a `# why:` comment.
- [x] 5.2 `rule_surface_explicit` fires on credential-named tools decorated with any of `@a2kit.read|write|list_|tool` (or bare-imported equivalents) when `surfaces=` is absent.
- [x] 5.3 Wired into `static.py` `_build_rules_table` as `A2K_SURFACE_EXPLICIT`.
- [x] 5.4 `tests/packages/lint/rules/test_surface.py` — 7 tests covering bare login fires, explicit Surface.CLI/ALL suppresses, non-credential names skipped, all four verbs covered, substring match.
- [x] 5.5 Full lint clean — `make lint` passes; A2K-SURFACE-EXPLICIT finds zero incidental issues in src/tests/examples (no credential-named a2kit tools exist yet outside the planned `connections` rewrite).

## 6. Documentation

- [x] 6.1 OPERATIONAL_CONTRACTS Q2 rewritten with four prescribed patterns (single-budget, multi-stage nested, silent degrade with `move_on_after`, cleanup-on-timeout) and the rationale for no decorator kwarg.
- [x] 6.2 README API-surface table updated: App entry mentions Router-as-plugin; Router entry mentions `providers`/lifecycle/`install`; new Surface entry; verb decorators mention `surfaces?`.
- [x] 6.3 README leading example switched to imperative composition with a "Style note" callout that fluent chain is shorthand. Second example (DI walkthrough) updated to match.
- [x] 6.4 `add_cli` deprecation warning explains the path forward inline at the call site; method docstring untouched (the warning surfaces the contract better than a docstring would).

## 7. Quality gates

- [x] 7.1 `uv run pytest -q --no-cov` — 684 passed (was 658 baseline; +26 new tests across Surface, surface filtering, Router extensions, connections router, A2K-SURFACE-EXPLICIT rule).
- [x] 7.2 `make lint` — 0 findings, including the new A2K-SURFACE-EXPLICIT rule which finds no incidental issues in src/tests/examples.
- [x] 7.3 `uv run ty check src/` — clean.
- [x] 7.4 Cold-start: 14.1ms (well under any budget).
- [x] 7.5 `openspec validate router-as-plugin-with-surfaces --strict` — green.
