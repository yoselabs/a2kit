## 1. Substrate signature splitter (foundational)

- [x] 1.1 Locate the current `install_mcp_signature` in the dispatch package; identify all call sites.
- [x] 1.2 Create `src/a2kit/packages/dispatch/substrate.py` (or equivalent home) with `install_substrate_signature(fn, substrate, container)` and `split_signature(fn, substrate, container) -> SplitSignature`.
- [x] 1.3 Define module-level `_FASTAPI_RESERVED` and `_FASTMCP_RESERVED` frozen sets per ADR 0020. *(Materialized as lazy `fastapi_reserved()` / `fastmcp_reserved()` accessors over `_FASTAPI_RESERVED_SPECS` / `_FASTMCP_RESERVED_SPECS` — preserves cold-start.)*
- [x] 1.4 Implement three-way classification: substrate-reserved → passthrough, Container-known via `has_provider` → DI, remainder → wire. Cover `Annotated[T, ...]`, `Optional[T]`, `Union[T, None]` unwrapping in tests.
- [x] 1.5 Write the wrapper generator: contextvar `_a2kit_scope`, `Container.call_scope` async-with, substrate-facing `__signature__` assigned to the wrapper. *(Option B per-substrate emission. FastMCP wrapper opens scope inside the wrapper body; MCP call sites still route through `install_mcp_signature` for now — wiring deferred to 1.6.)*
- [ ] 1.6 Update existing MCP call sites to call `install_substrate_signature(fn, "fastmcp", container)`. Run the full MCP test suite — all existing MCP tests pass byte-for-byte.
- [x] 1.7 Add unit tests for `split_signature` covering each bucket and edge cases (Annotated, Optional, Union, ForwardRef).
- [ ] 1.8 Delete (or rename) `install_mcp_signature` so any consumer importing the old name gets `ImportError`.

## 2. HTTP package skeleton

- [x] 2.1 Create `src/a2kit/packages/http/__init__.py` re-exporting `build_http_app` and `ApiSurface`.
- [x] 2.2 Create `src/a2kit/packages/http/build.py` with `build_http_app(runtime) -> fastapi.FastAPI`.
- [x] 2.3 Create `src/a2kit/packages/http/api.py` with the `ApiSurface` class — `get/post/put/delete/patch/options/head` methods, lazy `fastapi_app` property.
- [x] 2.4 Create `src/a2kit/packages/http/_scope.py` with the `_a2kit_scope` contextvar definition (single source of truth for HTTP-side per-call scope). *(Resolved: contextvar lives in `dispatch.substrate` — the wrapper that sets it lives there. `packages/http/build.py::_get_scope_contextvar` documents the rationale and re-exports for HTTP consumers; no separate `_scope.py` file.)*
- [x] 2.5 Implement `build_http_app`: walk `runtime.tools` (filter by `"api" in expose`), walk `runtime.api_routes`, call `install_substrate_signature` per registration, `fastapi.add_api_route(...)`. Default health route at `/api/health`. *(`expose` filter and `runtime.api_routes` registry land in Phase 4; for Phase 2 every projection tool is exposed and `api_surface` is passed positionally.)*
- [x] 2.6 Add `fastapi` to `pyproject.toml` dependencies. Confirm it is not eagerly imported by anything outside `packages/http/` and `packages/serve.py`'s lazy import block.

## 3. MCP surface wrapper

- [x] 3.1 Create `src/a2kit/packages/mcp/surface.py` with the `McpSurface` class — `.tool/.prompt/.resource` decorator methods, lazy `fastmcp_server` property.
- [ ] 3.2 Update `build_mcp_server` to register `runtime.mcp_features` alongside projection tools, walking both with `install_substrate_signature(fn, "fastmcp", container)`. *(Deferred with 1.6 — touches the MCP wrapper byte-for-byte gate.)*
- [ ] 3.3 Ensure existing MCP projection behaviour is unchanged — same MCP wire format, same Content shape, same FormatRoutingMiddleware integration. *(Verified via the existing MCP test suite passing on every commit so far.)*

## 4. App-level glue

- [x] 4.1 Add `App.api` lazy property returning `ApiSurface` instance bound to the app.
- [x] 4.2 Add `App.mcp` lazy property returning `McpSurface` instance bound to the app.
- [ ] 4.3 Add `expose: tuple[Literal["mcp","api"], ...] = ("mcp", "api")` and `authorize: Callable | None = None` kwargs to `@app.read/list/write` decorator functions. Empty `expose` raises `ValueError` at decoration.
- [ ] 4.4 Add `authorize=` kwarg to `app.api.<method>` and `app.mcp.<feature>` decorators (no `expose=` — they're single-surface; passing `expose=` raises `TypeError`).
- [ ] 4.5 Add `verb: Literal["read","list","write"]`, `expose: tuple[...]`, `authorize: Callable | None` fields to `ToolDescriptor`. Materialize at registration time.
- [ ] 4.6 Add `runtime.api_routes` and `runtime.mcp_features` registries to `AppRuntime`. Populate them at `build(app)` time from `App`'s collected registrations.

## 5. Auto-mount in serve

- [ ] 5.1 Update `build_parent_app` to determine mounts from runtime registrations:
  - FastAPI mounts if any projection tool has `"api" in expose` OR any `api_routes` entry exists.
  - FastMCP mounts if any projection tool has `"mcp" in expose` OR any `mcp_features` entry exists.
- [ ] 5.2 Remove the `mcp` and `rest` boolean kwargs from `build_parent_app`'s signature. Rename existing `rest=True` callers to nothing (kwarg-less call). Any external caller still passing `rest=` gets a `TypeError`.
- [ ] 5.3 Raise `ConfigError` if neither substrate would mount.
- [ ] 5.4 Update CLI `serve` callback in `packages/cli/builder.py` to drop the `--mcp` / `--rest` flag handling (replaced by auto-mount; `--select 'surface=...'` is a separate change).

## 6. Rename and removal

- [ ] 6.1 Delete `src/a2kit/packages/rest.py` outright. Python's native `ModuleNotFoundError: No module named 'a2kit.packages.rest'` satisfies AGENTS.md §1; no sentinel stub.
- [ ] 6.2 Update `src/a2kit/packages/serve.py` to import from `a2kit.packages.http` (no `rest`).
- [ ] 6.3 Find every reference to `build_rest_app` in the codebase. Update to `build_http_app`. Verify no stale references in tests, docs, or examples.
- [ ] 6.4 Update `a2kit.packages.lint` configuration if needed; existing import-discipline tests must pass.

## 7. Ruff banned-imports config

- [ ] 7.1 Add `[tool.ruff.lint.flake8-tidy-imports.banned-api]` or `[per-file-ignores]` section in `pyproject.toml` blocking `a2kit.packages.codemode` imports under `src/a2kit/packages/http/`.
- [ ] 7.2 Run `ruff check` and ensure no new violations.
- [ ] 7.3 Confirm the existing `A2K-LAYER` lint rule still passes — `http` is at L5 alongside `cli`, `mcp`, `codemode`, `otel` per the layer manifest.

## 8. Tests

- [ ] 8.1 `tests/test_cold_start.py` — assert `import a2kit` in a fresh interpreter does not load `fastapi` or `fastmcp`. Also assert `<app> --help` (subprocess) does not.
- [ ] 8.2 `tests/packages/dispatch/test_substrate_split.py` — three-way splitter against fixtures (substrate-reserved + Container-known + wire with `Annotated`/`Optional`/`Union`).
- [ ] 8.3 `tests/packages/dispatch/test_substrate_reserved_allowlist.py` — assert exact frozenset membership.
- [ ] 8.4 `tests/packages/http/test_multiplex.py` — register projection + `.api` route + `.mcp.tool`, exercise all three on multiplexed HTTP, assert shared `Database` singleton.
- [ ] 8.5 `tests/packages/http/test_scope_concurrency.py` — two concurrent FastAPI requests resolving a `Scope.SCOPED` provider get distinct instances.
- [ ] 8.6 `tests/packages/http/test_dependency_override.py` — `container.override(T, fake)` works (positive test). Docstring explains why FastAPI's `dependency_overrides[T]` is not the right seam for Container-known deps. Do not add a negative-assertion test for absence-of-FastAPI-feature.
- [ ] 8.7 `tests/packages/http/test_expose.py` — `expose=["mcp"]` hides the tool from `/api`; `expose=["api"]` hides from `/mcp`; default exposes both.
- [ ] 8.8 `tests/packages/http/test_auto_mount.py` — only `.api` registrations → only `/api` mount; only projection → both mounts; empty → `ConfigError`.
- [ ] 8.9 `tests/packages/http/test_openapi.py` — generated OpenAPI doc at `/api/openapi.json` contains the projection tool routes with correct schemas; Swagger UI at `/api/docs` is reachable and renders.

## 9. Documentation

- [ ] 9.1 Update README with three-decorator usage examples (projection, `.api.get`, `.mcp.prompt`).
- [ ] 9.2 Add ADR 0020 file at `docs/adr/0020-multi-surface-authoring.md` with the content drafted in conversation. Use the existing frontmatter schema.
- [ ] 9.3 Regenerate `docs/adr/INDEX.md` via `scripts/adr_index.py`.
- [ ] 9.4 Regenerate `docs/COMPONENT_MAP.md` via `scripts/component_map.py`.
- [ ] 9.5 Document the `container.override` test seam in `tests/packages/http/test_dependency_override.py` docstring and link from README's testing section.

## 10. Validation

- [ ] 10.1 `openspec validate add-multi-surface --strict` passes.
- [ ] 10.2 `make lint` green.
- [ ] 10.3 `make test` green (no test in `tests/` skipped or failing).
- [ ] 10.4 Coverage stays at or above the existing threshold (90%+).
- [ ] 10.5 Spec-drift gate (`tests/test_spec_symbol_drift.py`) passes — all symbols cited in updated specs resolve in live code.
