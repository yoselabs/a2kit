## 0. Prerequisites

- [x] 0.1 Confirm `v1-cleanup-debt` is applied (or in flight). This change builds on the `ToolContext` Protocol shape introduced there.
- [x] 0.2 Capture baseline: `uv run pytest -q` count + coverage; `make lint` exits 0; cold-start budgets met.

## 1. Core — `A2KitMeta.report_schema` + decorator kwarg

- [x] 1.1 Add `report_schema: dict[str, Any] | None = None` field to `A2KitMeta` in `src/a2kit/metadata.py`.
- [x] 1.2 Update `src/a2kit/tool.py` so `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, `@a2kit.tool` accept `report=ReportT` kwarg. When set, compute JSON schema via `ReportT.model_json_schema()` (Pydantic) or `pydantic.TypeAdapter(ReportT).json_schema()` (TypedDict) and stamp on the `A2KitMeta`.
- [x] 1.3 Add `ReportTypeMismatch` and `ReportTypeNotDeclared` to `src/a2kit/exceptions.py`.
- [x] 1.4 Mirror tests at `tests/test_metadata.py` (new file) covering: kwarg captured; schema correctness; missing kwarg leaves `report_schema=None`.

## 2. ToolContext Protocol — `report` + `event`

- [x] 2.1 Update `src/a2kit/__init__.py` `ToolContext` Protocol with `async def report(self, payload: Any) -> None:` and `async def event(self, name: str, **payload: Any) -> None:`.
- [x] 2.2 Implement on `src/a2kit/packages/mcp/context.py` — both methods route through `self._fastmcp_ctx.session.send_log_message(...)` with `level="report"` / `level="event"` and structured payload as `data`. For `report`: validate against `tool_meta.report_schema` (raise `ReportTypeMismatch` on fail) before emit; raise `ReportTypeNotDeclared` if `report_schema is None`.
- [x] 2.3 Implement on `src/a2kit/packages/cli/context.py` — both methods write to stderr with a recognizable prefix (`[report] ...`, `[event] name=... payload=...`).
- [x] 2.4 Mirror tests at `tests/packages/mcp/test_context.py` and `tests/packages/cli/test_context.py` covering: report happy path; report type mismatch; report not declared; event happy path; event with empty payload.

## 3. Kill-switch — env var + flag + app method

- [x] 3.1 Add `App.set_ldd(*, reports: bool = True, events: bool = True) -> "App"` to `src/a2kit/app.py`. Stores on `self._ldd_reports` / `self._ldd_events`.
- [x] 3.2 Add `App._ldd_from_env()` reading `A2KIT_LDD=off` once at construction. Set `_ldd_reports=False, _ldd_events=False` if env is `off`.
- [x] 3.3 Add `--no-reports` and `--no-events` flags at the CLI root in `src/a2kit/packages/cli/builder.py`. When set, override the App config for that invocation.
- [x] 3.4 Pass the resolved flags into the `ToolContext` impl at construction time. Both impls short-circuit `report` / `event` to no-op when disabled (after type validation for `report`).
- [x] 3.5 Mirror tests at `tests/test_app.py` (existing) covering: env-var disables; `set_ldd` disables; CLI flag disables; precedence (flag > app > env); disabled-but-still-validates.

## 3.5. Wire-format — relative `s.mmm` + terse rendering

- [x] 3.5.1 In both context impls, capture `_start_ts = time.monotonic()` at construction. Both `info`/`warning`/`error`/`report_progress`/`event`/`report` SHALL include the elapsed time on emission.
- [x] 3.5.2 CLI impl: rewrite `_emit` to format `[ +{elapsed:6.3f} {level:<8}] {msg} {kv}`. Update the existing log levels to share the same prefix.
- [x] 3.5.3 MCP impl: include `elapsed_ms: int(round((time.monotonic() - self._start_ts) * 1000))` in the `data` dict of every `notifications/message` payload.
- [x] 3.5.4 Update existing CLI context tests for the new prefix shape. Add tests for elapsed-ms in MCP impl.
- [x] 3.5.5 README adds a "Recommended client-side rendering" snippet so consumers of the MCP wire can render `data.elapsed_ms` consistently.

## 4. Schema dump — `<app> schema <tool>` includes report shape

- [x] 4.1 Update `src/a2kit/packages/cli/schemas.py::compute_schema` to include a `report_schema` field on the result when the tool's `A2KitMeta.report_schema` is non-None.
- [x] 4.2 Update the formatter that renders TOON / JSON schema dump output to include the report section.
- [x] 4.3 Mirror test at `tests/packages/cli/test_schemas.py` asserting report schema renders.

## 5. Lint rule — `A2K-LDD-REPORT-TYPE`

- [x] 5.1 Add the AST walker to `src/a2kit/packages/lint/rules/shape.py` (or split to a new `rules/ldd.py` if shape gets too crowded). Detect: tool body calls `ctx.report(...)` AND decorator has no `report=` kwarg → fire on call site. Detect: declared `ReportT` is defined inside a function/class (not module scope) → fire on the decorator kwarg.
- [x] 5.2 Wire the rule into `static.py`'s `RULES` dispatch tuple.
- [x] 5.3 Mirror tests at `tests/packages/lint/test_rules_ldd.py`. Cover: missing kwarg fires; module-scope ReportT silent; nested ReportT fires; tool without `ctx.report` calls silent.

## 6. Example — extend `examples/streaming_logger/`

- [x] 6.1 Add a new tool `import_csv_with_reports` to the streaming_logger example that uses `ctx.report(BatchReport(...))` + `ctx.event("phase.complete", ...)` alongside the existing `ctx.info` + `report_progress`.
- [x] 6.2 Define `BatchReport(BaseModel)` at module scope.
- [x] 6.3 Update the example README contrasting all four channels: when to use `info` vs `event` vs `report` vs `report_progress`.
- [x] 6.4 Mirror tests at `tests/examples/streaming_logger/test_reports.py` asserting reports + events emit during execution.

## 7. Documentation

- [x] 7.1 Add a "Logging + progress + reports + events" section to `README.md` with the four-channel decision table.
- [x] 7.2 Add an ANTIPATTERNS entry: "Don't fold structured findings into log strings — use `ctx.event` (typed name) or `ctx.report` (typed payload)."
- [x] 7.3 Add an ANTIPATTERNS entry: "Don't rely on env-only kill-switch in test code — use `app.set_ldd(...)` so tests are deterministic."
- [x] 7.4 Update `CHANGELOG.md` next-version section listing the new methods, kwarg, exceptions, lint rule, kill-switch.

## 8. Verification

- [x] 8.1 `uv run pytest -q` — all new tests pass; existing 454 still green.
- [x] 8.2 `make lint` exits 0 (includes A2K-LDD-REPORT-TYPE on src/, tests/, examples/).
- [x] 8.3 `uv run ty check src/` — All checks passed.
- [x] 8.4 Cold-start budgets unchanged: `import a2kit` < 100 ms; no new transitive imports.
- [x] 8.5 Smoke test (stdio): launch `examples.streaming_logger.server serve --transport=stdio`, drive a tool call, observe `notifications/message` with `level="report"` arriving before the tool's final return. Capture in test.
- [x] 8.6 Smoke test (CLI): `<app> tool import-csv ... --no-reports` produces zero `[report]` stderr lines but normal stdout return. Without the flag: stderr shows interleaved reports + events.
- [x] 8.7 Backwards compat: existing tools without `report=` kwarg unchanged; tracker example unchanged; streaming_logger original tool still works without reports.

## 9. Tag readiness — when ready to ship

- [ ] 9.1 Update `CHANGELOG.md` next-version entry to "released" status with date.
- [ ] 9.2 Pause for explicit user authorization before merging.
