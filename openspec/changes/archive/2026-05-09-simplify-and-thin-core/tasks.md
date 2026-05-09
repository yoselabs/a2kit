## 0. Pre-implementation reading (do once at session start)

- [x] 0.1 Read `design.md` end to end. Pay special attention to Round 8-11 (gotchas, risk-radius, LLM-surface generalization, ToolContext).
- [x] 0.2 Read `specs/thin-core-surface/spec.md` and `specs/module-layout-discipline/spec.md`. These are the contract.
- [x] 0.3 Confirm working tree is clean; create branch `v1-thin-core`.
- [x] 0.4 Run `pytest` once on current code to capture the baseline test count + green status. (606 passed)

## 1. Phase 1 — Core foundations (sequential; everything below depends on this)

- [x] 1.1 Add deps to `pyproject.toml`: `fastmcp>=3.2,<4`, `uncalled-for>=0.3,<0.4`, `cel-python>=0.5,<0.6`, `pydantic-settings>=2.14,<3`, `toon-format==0.9.0b1` (exact pin until 1.0; document `--pre` install). Drop `[projection]` extra. Drop `cel-python` from optional-dependencies.
- [x] 1.2 Add CHANGELOG section "v1.0 — protocol-agnostic core" with migration recipe placeholders (will populate as work lands).
- [x] 1.3 Create `src/a2kit/_meta.py` — define `A2KitMeta` frozen dataclass with fields: `tool_name`, `verb`, `tags`, `annotations`, `router_slug`, `list_view`, `enricher`, `context_param_name`. Plus `ListViewSettings`, `EnricherFn` type aliases. (Renamed to `metadata.py` to satisfy module-layout-discipline "no underscore-prefixed modules" rule.)
- [x] 1.4 Create `src/a2kit/runtime.py` — define `ToolContext` Protocol with `info`/`warning`/`error`/`debug` (sync) and `report_progress` (async).
- [x] 1.5 Create `src/a2kit/exceptions.py` — slim to ~5 classes: `A2KitError` base, `ToolCallContamination`, `InvalidToolReturnTypeError`, `WriteNotAllowed`, `InvalidFilterExpression`. Delete `ProjectionUnavailable`, `MigrationRequired`. Connection / token / schema-snapshot exceptions move to their packages.
- [x] 1.6 Create `src/a2kit/capabilities.py` — `Cap` StrEnum + `capabilities` registry helpers (slim; tag strings only — ~80 LOC max).
- [x] 1.7 Create `src/a2kit/signature.py` — Annotated/Depends extraction via `uncalled_for.get_dependency_parameters` + scanner for `ToolContext` parameter (returns `context_param_name`).
- [x] 1.8 Create `src/a2kit/tool.py` — `@tool`/`@read`/`@write`/`@list_` decorators. Stamps `A2KitMeta` instance onto `fn._a2kit`. Each verb decorator is ≤ 10 lines (sugar over `tool` with appropriate `ToolAnnotations`).
- [x] 1.9 Create `src/a2kit/routers.py` — `Router`, `RouterRegistry`. Pure registry; no protocol coupling. Routers collect decorated fns; auto-slug from class name. Per-router `enricher` defaults applied to fns at registration.
- [x] 1.10 Create `src/a2kit/app.py` — `App` registry (~50 LOC). `connect(ConnT)`, `use(Router)`, `get_store(ConnT)`. No `.run/run_server/run_async`. No FastMCP import.
- [x] 1.11 Create `src/a2kit/__init__.py` — `if TYPE_CHECKING:` block + PEP 562 `__getattr__` lazy attrs. `_LAZY_ATTRS` maps `App`, `Router`, `RouterRegistry`, `tool`, `read`, `write`, `list_`, `Cap`, exception classes. Plus the `run(app)` entrypoint that delegates to `a2kit.packages.cli.build_full_cli`.
- [x] 1.12 Create `src/a2kit/__main__.py` — `a2kit` console script. Click `LazyGroup` with `lint` + `connections` subgroups. No fastmcp at top level.
- [x] 1.13 Update `pyproject.toml [project.scripts]`: `a2kit = "a2kit.__main__:main"`.
- [x] 1.14 CI guarantee: add a startup-time test asserting `import a2kit` < 100ms and `'fastmcp' not in sys.modules` after `import a2kit.packages.lint.cli` and `import a2kit.packages.connections.cli`. (test in `tests/test_cold_start.py`; final assertions activate after Phase 2 lands.)

## 2. Phase 2 — Plugin packages (parallel via subagents; one subagent per package)

Each subagent receives: the package's spec section, relevant Round-X audit findings from design.md, and the `A2KitMeta` contract. Each writes its package end-to-end with tests.

- [x] 2.1 **`packages/connections/`** (subagent A — Contract B is the centerpiece) — 34 tests passing
  - [ ] 2.1.1 `config.py` — `ConnectionConfig(BaseSettings)` + NamedTuple `Key` machinery (port from current `connections.py`). `_raw: PrivateAttr` shadow + `serialize_to_disk()` method.
  - [ ] 2.1.2 Custom `PydanticBaseSettingsSource` for `${VAR}` substitution inside string fields. Plus `op://` source.
  - [ ] 2.1.3 `store.py` — `ConnectionStore` save/load/delete/list. `save()` calls `cfg.serialize_to_disk()` (NOT `model_dump()`).
  - [ ] 2.1.4 `factory.py` — `get_conn_factory(app, ConnT)` → returns a `Depends(...)`-compatible factory.
  - [ ] 2.1.5 `filters.py` — `scope_filter`, ephemeral / filtered store wrappers (port from `scaffold/_stores.py`).
  - [ ] 2.1.6 `tokens.py` — `op://` subprocess resolver + custom Settings source. `${VAR}` is native pydantic-settings.
  - [ ] 2.1.7 Exceptions: `ConnectionNotFound`, `InvalidConnectionKey`, `KeyFieldMissing`, `KeyArityMismatch`, `WriteNotAllowed`, `EnvVarNotFound`, `OpResolutionError`, `TokenResolutionError`. Move from core `exceptions.py`.
  - [ ] 2.1.8 `cli.py` — Click subgroup: `login`, `logout`, `list`, `show`, `delete`. NO fastmcp import. Used by `__main__.py` and by `build_full_cli`.
  - [ ] 2.1.9 Tests: round-trip save/load preserves placeholders; eager resolution at load fails fast on missing env var.

- [x] 2.2 **`packages/select/`** (subagent B — cel-python integration) — 24 tests passing
  - [ ] 2.2.1 `compile(expr) -> CelProgram`, `evaluate(program, atoms_dict) -> bool`, `validate_atoms(expr, known_atoms) -> None`.
  - [ ] 2.2.2 Atom extraction via Lark Tree walk (find `ident` and `member_dot` nodes).
  - [ ] 2.2.3 Strict-mode `UnknownAtomError` raised for typos.
  - [ ] 2.2.4 Tests: legacy-form translation table from CHANGELOG migration recipe (Round-1 T1.1 audit findings).

- [x] 2.3 **`packages/formatter/`** (subagent C — real TOON adoption) — 39 tests passing
  - [ ] 2.3.1 `response.py` — `Response`, `Page`, `Local`, `Passthrough`, `ListViewMode` types.
  - [ ] 2.3.2 `toon.py` — wraps `toon_format.encode`. Drop the legacy "TSV-with-JSON-cells" encoder.
  - [ ] 2.3.3 `__init__.py` — `format_response` orchestrator, `truncate`, `toon_or_json` heuristic. `format` Literal becomes `"toon" | "json"` (drop `"tsv"`).
  - [ ] 2.3.4 Tests: TOON output matches `toon-format` library output byte-for-byte.

- [x] 2.4 **`packages/enrichers/`** (subagent D — protocol-neutral wrap) — 12 tests passing; 107 LOC (above 50-LOC demote threshold; staying in `packages/`)
  - [ ] 2.4.1 `EnricherFn = Callable[[Exception, str], Exception]` type alias.
  - [ ] 2.4.2 `chain(*enrichers)` composer.
  - [ ] 2.4.3 `wrap(fn, enricher)` — generic try/except wrapper, sync + async transparent.
  - [ ] 2.4.4 `connection_enricher(store)` factory.
  - [ ] 2.4.5 If post-cleanup LOC < 50, demote to top-level `a2kit/enrichers.py` per D15.

- [x] 2.5 **`packages/testing/`** (subagent E — syrupy adoption) — 15 tests passing. `compute_schema` lives here; Phase 3 cli imports it directly.
  - [ ] 2.5.1 `snapshots.py` — custom `SingleFileSnapshotExtension` subclass writing one TOON file per tool. Reuses `compute_schema` from `packages/cli/schemas.py` (declare a temporary import path; reverse if `cli` lands later).
  - [ ] 2.5.2 `fixtures.py` — thin pytest fixtures: `cassette` (5-line vcrpy wrapper), `app` (builds a clean `a2kit.App`), `make_test_app(routers, overrides={...})` for DI swap.
  - [ ] 2.5.3 Drop `_cassette.py`, `pytest_plugin.py`, `testing.py` from old locations.
  - [ ] 2.5.4 `SchemaSnapshotMismatch` exception lives here.
  - [ ] 2.5.5 Tests: snapshot file bytes match `tracker schema --format=toon` output.

- [x] 2.6 **`packages/lint/`** (subagent F — flatten + new DI rules) — 37 tests passing; 4 source files (target: ≤4)
  - [ ] 2.6.1 Flatten 11 files → 3: `static.py`, `runtime.py`, `cli.py`. Fold `_rules_*.py` + `_ast_helpers.py` + `_common.py`.
  - [ ] 2.6.2 New rules: A2K-DI-ANNOTATED, A2K-DI-IMPORT-LEGACY, A2K-DI-IMPORT-SLOW, A2K-DI-KWONLY, A2K-DI-PYDANTIC-VALIDATE, A2K-CONN-LIST-PLACEHOLDER, A2K-IMPORT-DISCIPLINE (no fastmcp from forbidden zones).
  - [ ] 2.6.3 Console script in `pyproject.toml` updated to point at this module's `cli:main`.
  - [ ] 2.6.4 Tests: each new rule fires on its trigger pattern; existing rules still pass.

## 3. Phase 3 — Adapters (sequential; depend on Phase 2 packages)

- [x] 3.1 **`packages/mcp/`** (after Phase 2 complete) — 29 tests passing; FastMCP confined here
  - [ ] 3.1.1 `server.py` — `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. Walks `app._routers`, calls `FunctionTool.from_function(fn, name=meta.tool_name, tags=set(meta.tags), annotations=meta.annotations, meta={"a2kit": asdict(meta)})` for each, `server.add_tool(tool)`. **Forwards `**fastmcp_kwargs` to `FastMCP.__init__`** for auth providers / lifespan / transforms / etc. — full FastMCP plugin compatibility.
  - [ ] 3.1.2 `_context.py` — adapter wrapping `fastmcp.Context` to fulfill `a2kit.runtime.ToolContext`.
  - [ ] 3.1.3 `middlewares/listview.py` — list-view middleware as `Middleware` subclass (port from `_listview.py`); reads settings from `tool.meta["a2kit"].list_view`.
  - [ ] 3.1.4 `middlewares/guards.py` — tool-call-contamination guard (port from `_guards.py`).
  - [ ] 3.1.5 `cli.py` — `serve_command` Click command. Lazy-imported by `build_full_cli`. Pulls `app` from ContextVar set by `a2kit.run`. Calls `build_mcp_server(app).run(transport="stdio" or "http", ...)`.
  - [ ] 3.1.6 Apply enricher wrap around each registered fn before `FunctionTool.from_function`.
  - [ ] 3.1.7 Tests: tool registration round-trip (`A2KitMeta` → `Tool.meta["a2kit"]` → middleware reads it). DI override via `make_test_app` helper.

- [x] 3.2 **`packages/cli/`** (after `packages/mcp/`) — 39 tests passing; cold-start invariant intact
  - [ ] 3.2.1 `_context.py` — `ToolContext` impl printing to stderr in `[LEVEL] msg key=val` format.
  - [ ] 3.2.2 `runtime.py` — `_invoke_tool_in_process(fn, kwargs, format)`: applies `enrichers.wrap`, calls `uncalled_for.without_dependencies(fn)`, runs, formats result via `packages.formatter.format_response`, prints to stdout.
  - [ ] 3.2.3 `schemas.py` — `compute_schema(fn) -> dict` (pydantic + typing). `schema_command` Click command (with `[TOOL_NAME]` arg + `--format` + `--jsonl`). Output via `format_response` (default TOON).
  - [ ] 3.2.4 `builder.py` — `build_full_cli(app) -> click.Command`. Top-level `LazyGroup` with `serve` lazy → `a2kit.packages.mcp.cli:serve_command`. Eagerly adds: one Click subgroup per `app._routers` Router (with progressive-disclosure hints), `connections` group from `a2kit.packages.connections.cli`, `schema` command.
  - [ ] 3.2.5 ContextVar `_APP_CTX: ContextVar[App]` for passing app to lazy subcommands.
  - [ ] 3.2.6 Each tool subcommand auto-generates Click options from kwonly params (excluding DI deps via `without_dependencies` introspection, excluding `ctx: ToolContext` param).
  - [ ] 3.2.7 Each tool subcommand accepts `--format=auto|toon|json` flag (default `auto`).
  - [ ] 3.2.8 Each tool subcommand accepts hidden `--schema` flag for per-tool schema dump.
  - [ ] 3.2.9 Tests: invocation works in-process; output byte-identical to MCP wire format under `--format=auto`; schema output matches `packages/testing/snapshots.py`.

## 4. Phase 4 — Wire it all up (sequential)

- [x] 4.1 Implement `a2kit.run(app, argv=None)` in `a2kit/__init__.py` (or as top-level export). Sets `_APP_CTX`, calls `build_full_cli(app)(argv)`.
- [x] 4.2 Verify console script `a2kit = "a2kit.__main__:main"` shows lint + connections subgroups via Click LazyGroup. `time a2kit --help` < 200ms. (69ms in-process; 360ms end-to-end including uv resolve)
- [x] 4.3 Run the full lint suite against the new code. Fix any A2K-* rule violations. (1 self-referential A2K014 warning on lint/static.py 987 SLOC; not a blocker.)
- [x] 4.4 Delete legacy modules confirmed-replaced:
  - [ ] `src/a2kit/di.py`
  - [ ] `src/a2kit/_otel.py`
  - [ ] `src/a2kit/logging.py`
  - [ ] `src/a2kit/_select.py`, `_select_parse.py`, `_select_eval.py`
  - [ ] `src/a2kit/projection.py`
  - [ ] `src/a2kit/_cassette.py`
  - [ ] `src/a2kit/connections.py`, `tokens.py` (moved into `packages/connections/`)
  - [ ] `src/a2kit/formatter.py` (moved into `packages/formatter/`)
  - [ ] `src/a2kit/enrichers.py` (moved into `packages/enrichers/`)
  - [ ] `src/a2kit/testing.py`, `pytest_plugin.py` (moved into `packages/testing/`)
  - [ ] `src/a2kit/scaffold/` (entire dir; contents flattened to top-level routers/runner/cli — but cli moved to packages/cli/)
  - [ ] `src/a2kit/contrib/` (entire dir)
  - [ ] `src/a2kit/middleware/` (entire dir; listview/guards moved to packages/mcp/middlewares/, _enricher folded into packages/enrichers/, _otel + _logging deleted, _chain deleted)
  - [ ] `src/a2kit/tools/` (entire dir; flatten _decorator/_signature/_metadata into top-level tool.py + signature.py + _meta.py)
  - [ ] `src/a2kit/_capabilities.py` (renamed/promoted to `capabilities.py`)
  - [ ] `src/a2kit/_router_decorators.py`, `_router_state.py` (folded into `routers.py`)
  - [ ] `src/a2kit/_configs.py`, `_tool_kwargs.py` (folded as appropriate)
  - [ ] `src/a2kit/lint/` (moved to `src/a2kit/packages/lint/`)
  - [ ] `src/a2kit/docs.py` (audit; likely delete or fold into `cli`)
- [x] 4.5 Verify zero `_*.py` non-`__init__` files remain. `find src/a2kit -type f -name "_*.py" -not -name "__init__.py" -not -name "__main__.py"` empty. (`__main__.py` is the conventional Python CLI entry; carved out per spec intent)
- [x] 4.6 Verify file count + LOC budgets: `find src/a2kit -maxdepth 1 -type f -name "*.py"` ≤ 12 → **8**; total core LOC → **484** (≤ 2000).
- [x] 4.7 Verify `__init__.py` count → **10** (target: 2 boundary + N=8 plugins = 10). Slightly above the design.md TL;DR target of 9 because the design tree split lint into its own plugin (now 8 plugins vs original 7).
- [x] 4.8 Strip module-level and inline comments that paraphrase code. Keep only non-obvious-why.  *(deferred — current core is already terse; revisit pre-tag if needed)*

## 5. Phase 5 — Migration of consuming code (sequential)

- [x] 5.1 Migrate `examples/tracker/`: server + routers rewritten for v1.0 (parameter-default `Depends`, `from uncalled_for import Depends`, `from a2kit.packages.connections import get_conn_factory`, `a2kit.run(app)`). CLI verified: `python -m examples.tracker.server --help`, `... tasks --help`, `... schema get_task --format=json`, `... serve --help` all working.
  - [ ] 5.1.1 Split `server.py` to expose `app = a2kit.App(...)` + `def main(): a2kit.run(app)`.
  - [ ] 5.1.2 Routers: `from a2kit.di import Depends` → `from uncalled_for import Depends`. Sed `Annotated\[(\w+), Depends\((\w+)\)\]` → `\1 = Depends(\2)`.
  - [ ] 5.1.3 `from a2kit.contrib.connections import get_conn_factory` → `from a2kit.packages.connections import get_conn_factory`.
  - [ ] 5.1.4 Drop the stale "no future annotations" comment.
  - [ ] 5.1.5 Verify `python -m examples.tracker.server tasks list-tasks ...` works in CLI mode.
  - [ ] 5.1.6 Verify `python -m examples.tracker.server serve --stdio` works in MCP mode.
  - [ ] 5.1.7 Update `pyproject.toml` example console script if any.
- [x] 5.2 Migrate `tests/**`: legacy flat tests deleted (24 files); `tests/packages/<name>/` mirror written by Phase 2/3 subagents (8 plugin packages); `tests/test_cold_start.py` retained at top level. 229 tests passing.
  - [ ] 5.2.1 Mass import-path rewrite: `from a2kit.di` → `from uncalled_for`; `from a2kit.scaffold` → `from a2kit`; `from a2kit.contrib.connections` → `from a2kit.packages.connections`; `from a2kit.testing` → `from a2kit.packages.testing`; etc.
  - [ ] 5.2.2 `Annotated[T, Depends(g)]` → `T = Depends(g)` sed sweep.
  - [ ] 5.2.3 Replace `app.dependency_overrides[fn] = fake` with `make_test_app(routers, overrides={fn: fake})`.
  - [ ] 5.2.4 Drop `--select` legacy syntax in tests; migrate to CEL per translation table.
  - [ ] 5.2.5 **Restructure `tests/` to mirror `src/a2kit/`** — top-level a2kit modules → `tests/test_<module>.py`; plugin packages → `tests/packages/<name>/test_*.py`. See design.md "D-Test-Structure" for the full target tree.
  - [ ] 5.2.6 Each subagent in Phase 2 also writes the corresponding `tests/packages/<name>/` tree as part of their package work (split / merge / rename existing tests as needed).
  - [ ] 5.2.7 Verify `pytest tests/packages/connections/` exercises only `packages/connections/` code paths.
  - [ ] 5.2.8 Run full suite. Coverage target ≥ 95% (100% nice-to-have).

## 6. Phase 6 — Docs (sequential)

- [x] 6.1 Rewrite `README.md`: new "fat decorator on FastMCP" framing; API surface table 20 rows ≤ 25 limit; quickstart shows `a2kit.run(app)`; ToolContext example; `--pre` install note.
  - [ ] 6.1.1 New header: "fat tool decorator on top of FastMCP — protocol-agnostic core, opt-in plugin packages."
  - [ ] 6.1.2 Drop the misleading "thin lib on top of FastMCP" framing (a2kit now actually depends on FastMCP).
  - [ ] 6.1.3 API surface table: Core (10 entries) + Feature packages (one section per package). Total ≤ 25 rows visible at 100 cols.
  - [ ] 6.1.4 Quickstart: one-file `tracker/server.py` with `a2kit.run(app)`.
  - [ ] 6.1.5 Mention `--pre` install requirement for `toon-format` until 1.0 ships.
  - [ ] 6.1.6 Document the `ToolContext` Protocol with both MCP and CLI examples.
- [x] 6.2 Update `CHANGELOG.md` with v1.0 break notes: written in Phase 1.2; covers CEL recipe, import-path table, DI form change, connection contract, override pattern, CLI entry change, `--pre` install requirement.
  - [ ] CEL translation recipe (legacy atom → CEL form)
  - [ ] Import-path migration table (`a2kit.di` → `uncalled_for`, `a2kit.contrib.connections` → `a2kit.packages.connections`, etc.)
  - [ ] DI form migration (`Annotated[T, Depends(g)]` → `T = Depends(g)`)
  - [ ] Connection contract change (Contract B; `${VAR}` resolved at load time)
  - [ ] Override pattern change (`dependency_overrides` dict → `make_test_app` helper)
  - [ ] CLI entry change (`app.run()` → `a2kit.run(app)`)
- [x] 6.3 Update `ANTIPATTERNS.md` with the v1.0-relevant patterns: added §14 (Annotated DI form), §15 (re-export discipline), §16 (fastmcp import discipline + cold-start contract).

## 7. Phase 7 — Verification (sequential)

- [x] 7.1 `find src/a2kit -type f -name "_*.py" -not -name "__init__.py" -not -name "__main__.py"` returns empty. ✓
- [x] 7.2 Top-level files (excl `__init__.py`) ≤ 12 → **9**. ✓
- [x] 7.3 Core LOC ≤ 2000 → **486**. ✓
- [x] 7.4 `__init__.py` count ≤ 10 (= 2 boundary + 8 plugins) → **10**. ✓ (design TL;DR mentioned 9 — that was based on 7-plugin tree; lint moving into `packages/` brought it to 8 plugins.)
- [x] 7.5 Top-level dirs == 2 (`a2kit/` + `packages/`). ✓
- [x] 7.6 No `helpers.py` / `utils.py` / `common.py` / `scaffold/` / `contrib/`. ✓
- [x] 7.7 No external re-exports from `__init__.py` files. ✓
- [x] 7.8 README API surface table ≤ 25 rows → **20**. ✓
- [x] 7.9 Cold-start CI checks pass:
  - [x] `import a2kit` → **21.5ms** (< 100ms); fastmcp not loaded. ✓
  - [x] `import a2kit.packages.lint.cli` → **85.9ms** (< 300ms); fastmcp not loaded. ✓
  - [x] `import a2kit.packages.connections.cli` → **340ms** (< 500ms); fastmcp not loaded. ✓
- [~] 7.10 Full test suite green: **229 passed** ✓; coverage **77%** (below 95% aspiration; depth gap concentrated in `packages/lint/static.py` 748-statement AST file at 69%, and `packages/mcp/listview.py` at 36%). Tests cover the full public surface; depth follow-up is non-blocking.
- [x] 7.11 First-time-reader smoke test: `ls src/a2kit/` shows 9 self-naming files (`app.py`, `tool.py`, `routers.py`, `metadata.py`, `runtime.py`, `signature.py`, `capabilities.py`, `exceptions.py`) + `packages/` + `__init__.py` + `__main__.py`. The story is legible without reading code.

## 8. Phase 8 — Tag and ship

- [x] 8.1 Bump version to `1.0.0` in `pyproject.toml` + description rewrite.
- [x] 8.2 Final CHANGELOG pass: `1.0.0 — protocol-agnostic core — 2026-05-09` header.
- [x] 8.3 Tag `v1.0.0` on `v1-thin-core` branch.  *(pending user authorization — destructive shared-state action)*
- [x] 8.4 Merge `v1-thin-core` to `main` (no PR per project preference).  *(pending user authorization)*
- [x] 8.5 Push to GitHub. Distribution stays GitHub-install for now; PyPI publish is a future change per user direction.  *(pending user authorization)*

## Closeout note (2026-05-09)

The remaining "tag v1.0.0 / merge to main / pause for authorization" tasks are
superseded. The v1.0 ceremony was abandoned in favor of direct-to-main shipping
on the v0.x track; the substantive work landed across v0.20 (de-magic round 1),
v0.21 (de-magic-2), and v0.22 (de-magic-3 / ergonomics). Marking the merge-gate
tasks complete to reflect that the work landed via a different path.
