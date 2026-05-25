## 0. Prerequisites

- [ ] 0.1 Confirm `v1-cleanup-debt` and `test-quality-via-mutmut` changes are applied or running. Pushdown builds on the v1.0 listview kit and must not break A2K-TEST-MIRROR.
- [ ] 0.2 Capture baseline: `uv run pytest -q --no-cov` count; `make lint` exits 0; cold-start budgets met.

## 1. Core — `Pushdown` Protocol + `Query[T]`

- [ ] 1.1 Create `src/a2kit/pushdown.py` with `Pushdown(Protocol[Q])` (`runtime_checkable`), `Query[T]` wrapper (frozen dataclass), `PushdownNotSupported` exception. Target ≤ 50 LOC.
- [ ] 1.2 Re-export `Query` and `PushdownNotSupported` from `a2kit/__init__.py` lazy-attrs map (`Pushdown` is also exposed for type-only use under `TYPE_CHECKING`).
- [ ] 1.3 Verify cold-start: `import a2kit` still under 100 ms; no new transitive imports.
- [ ] 1.4 Create mirror test `tests/test_pushdown.py` with: protocol conformance check, `Query` round-trip, `PushdownNotSupported` raised cleanly, lazy-attr access from `a2kit` namespace.

## 2. Listview branch — middleware + CLI runtime

- [ ] 2.1 Extract the existing post-hoc listview implementation from `src/a2kit/packages/mcp/listview.py` into a shared `_post_hoc(rows, *, filter_expr, fields, cursor, page_size)` helper.
- [ ] 2.2 Add the rewrite-then-execute branch: if the tool result is a `Query[T]`, call `adapter.filter`/`fields`/`page` then `await adapter.execute(state)`.
- [ ] 2.3 Add the fallback branch: catch `PushdownNotSupported`, call `adapter.execute(state)` to materialize, then run `_post_hoc` on the materialized rows. Emit a debug log line at the boundary.
- [ ] 2.4 Mirror the same logic into `src/a2kit/packages/cli/runtime.py`. Both adapters share the same `apply_listview` helper to avoid drift.
- [ ] 2.5 Update `tests/packages/mcp/test_listview.py` with: pushdown happy path; PushdownNotSupported fallback; existing list-result path still green.
- [ ] 2.6 Add `tests/packages/cli/test_runtime.py` cases mirroring (2.5) for the CLI invocation flow.

## 3. SQL adapter — `packages/pushdown_sql/`

- [ ] 3.1 Create `src/a2kit/packages/pushdown_sql/{__init__.py, adapter.py, cel_to_sql.py}`. `__init__.py` lazily exposes `SqlPushdown`.
- [ ] 3.2 Implement `SqlPushdown` matching the `Pushdown` Protocol. State `Q` is a typed `dataclass`: `table`, `where`, `select`, `limit`, `offset`, `params`.
- [ ] 3.3 Implement `cel_to_sql(expr) -> tuple[str, list[Any]]` covering `==`, `!=`, `<`, `<=`, `>`, `>=`, `&&`, `||`, `!`, `in`, single-level field access. Raise `PushdownNotSupported` for any other AST shape.
- [ ] 3.4 Parameterize all user input — never concatenate strings into SQL. Add a focused negative test: a CEL string containing `"; DROP TABLE …"` MUST land as a bound parameter, never as raw SQL.
- [ ] 3.5 Implement `page(state, cursor, size)` with base64-encoded integer-offset cursors.
- [ ] 3.6 `execute(state)` builds the SQL, runs against a DB-API connection (sync drivers wrapped via `asyncio.to_thread`), returns `list[dict]`.
- [ ] 3.7 Add `[project.optional-dependencies] pushdown-sql = []` to `pyproject.toml` (no runtime deps; user supplies the driver).
- [ ] 3.8 Mirror tests at `tests/packages/pushdown_sql/{test_adapter.py, test_cel_to_sql.py}` against in-memory `sqlite3`. Cover: simple equality, compound boolean, `in` clause, fields projection, pagination, injection-safety, untranslatable CEL → `PushdownNotSupported`, end-to-end `execute()`.

## 4. JQL adapter — `packages/pushdown_jql/`

- [ ] 4.1 Create `src/a2kit/packages/pushdown_jql/{__init__.py, adapter.py, cel_to_jql.py}`.
- [ ] 4.2 Implement `JqlPushdown(client: httpx.AsyncClient, base_url: str)`. State `Q` carries the accumulated JQL string and REST query params dict.
- [ ] 4.3 Implement `cel_to_jql(expr) -> str` covering equality, comparison, `in` clauses, boolean compounds. Raise `PushdownNotSupported` otherwise.
- [ ] 4.4 `fields(state, names)` sets the `fields=` query param. `page(state, cursor, size)` sets `startAt` + `maxResults`.
- [ ] 4.5 `execute(state)` issues an authenticated GET (or POST for long JQL) and returns the response's `"issues"` array.
- [ ] 4.6 Add `[project.optional-dependencies] pushdown-jql = ["httpx>=0.27"]`.
- [ ] 4.7 Mirror tests at `tests/packages/pushdown_jql/` using `vcrpy` cassettes. Record once against a real Atlassian instance (or a mocked one); replay in CI.

## 5. REST adapter — `packages/pushdown_rest/`

- [ ] 5.1 Create `src/a2kit/packages/pushdown_rest/{__init__.py, adapter.py}`.
- [ ] 5.2 Implement `RestPushdown(endpoint, *, filter_param=None, fields_param=None, cursor_param=None, size_param=None, results_path=None, cel_to_query=None)`.
- [ ] 5.3 Each method gracefully raises `PushdownNotSupported` if the relevant param config is missing — the middleware then falls back to post-hoc on that dimension.
- [ ] 5.4 `execute(state)` GETs the endpoint with accumulated query params; resolves nested response paths via `results_path` (e.g. `"data.items"`).
- [ ] 5.5 Add `[project.optional-dependencies] pushdown-rest = ["httpx>=0.27"]`.
- [ ] 5.6 Mirror tests at `tests/packages/pushdown_rest/` using `httpx.MockTransport` for deterministic, no-network test runs.

## 6. Lint rule — A2K-PUSHDOWN-MISMATCH

- [ ] 6.1 Add `src/a2kit/packages/lint/rules/pushdown.py` implementing the AST detector: tool fn returns `Query[T]` annotation but `@a2kit.list_()` decorator has no `list_view=...` kwarg.
- [ ] 6.2 Wire the rule into `static.py`'s `RULES` dispatch tuple.
- [ ] 6.3 Mirror test at `tests/packages/lint/rules/test_pushdown.py`. Cover: fires on mismatch; silent on match; silent on tools that don't return `Query[T]`.

## 7. Example — `examples/sql_pushdown/`

- [ ] 7.1 Create `examples/sql_pushdown/{__init__.py, server.py, models.py, db.py, routers.py, README.md}`.
- [ ] 7.2 `db.py` builds an in-memory sqlite database with `tasks` and `projects` tables seeded with sample rows.
- [ ] 7.3 `routers.py` exposes a `TasksRouter` whose `list_tasks` and `search_tasks` tools return `Query[Task]` via the SQL adapter.
- [ ] 7.4 `server.py` wires `app.use_factory(get_db_factory(app), as_=get_db)` (matching the v1-cleanup-debt pattern).
- [ ] 7.5 `README.md` walks through the listview kwargs (`filter`, `fields`, `cursor`, `page_size`) and shows the SQL the adapter generates for each.
- [ ] 7.6 Smoke: `uv run python -m examples.sql_pushdown.server --help` works; `... tasks list-tasks --filter='status==open' --fields=id,title --page-size=5` returns 5 rows; the SQL emitted matches expectations (verifiable via debug log).
- [ ] 7.7 Mirror tests at `tests/examples/sql_pushdown/test_server.py`.

## 8. Documentation

- [ ] 8.1 Add a "Pushdown listview — when listview runs at the backend" section to `README.md` explaining the contract.
- [ ] 8.2 Add ANTIPATTERNS entry: "post-hoc filtering of large datasets" — mitigation: implement a `Pushdown` adapter for the backend.
- [ ] 8.3 Update `CHANGELOG.md` next-version section with the pushdown rollout.
- [ ] 8.4 Add per-adapter `README.md` to each `packages/pushdown_*/` documenting CEL coverage, configuration, and limits.

## 9. Verification

- [ ] 9.1 `uv run pytest -q --no-cov` — all new mirror tests pass; existing 252 still green.
- [ ] 9.2 `make lint` exits 0 (includes A2K-PUSHDOWN-MISMATCH and A2K-TEST-MIRROR for new files).
- [ ] 9.3 `uv run ty check src/` — All checks passed.
- [ ] 9.4 Cold-start budgets unchanged: `import a2kit` < 100 ms; `import a2kit.packages.cli.builder` does not load fastmcp; `import a2kit.packages.pushdown_sql` does not eagerly load any DB driver.
- [ ] 9.5 Pushdown happy path: SQL adapter rewrites listview kwargs into `WHERE` + `SELECT` + `LIMIT/OFFSET` and returns only matching rows.
- [ ] 9.6 Pushdown fallback path: untranslatable CEL → `PushdownNotSupported` → adapter executes the un-pushed query → post-hoc applies filter on materialized rows. Verified via test.
- [ ] 9.7 Backwards compat: tracker example unchanged; tools returning `list[dict]` produce byte-identical output.
- [ ] 9.8 If `test-quality-via-mutmut` is applied, run `make mutate-fast` against changed files; aggregate mutation score on new pushdown code ≥ 80 %.

## 10. Tag readiness — when ready to ship

- [ ] 10.1 Update `CHANGELOG.md` next-version entry to "released" status with date.
- [ ] 10.2 Pause for explicit user authorization before merging.
