# a2kit — v0.11+ todo

Captured from contract / asyncio / OTel audit (2026-05-08, post v0.10.0).

Priority order for this turn: **types & consumer API first**, then async, then OTel.

---

## P0 — public API / vocabulary  ✅ DONE (v0.11.0.dev0)

- [x] Moved `ConnectionInfoLike` / `ConnectionStoreLike` → `connections.py` (re-exported from `errors.py` shim).
- [x] Renamed `a2kit.errors` → `a2kit.enrichers`; `a2kit.errors` is now a `DeprecationWarning` shim (removed in v0.13).
- [x] Dropped `A2KIT_CONFIG_HOME` self-alias; raises `ImportError` with hint pointing to `ENV_CONFIG_HOME`.
- [x] Replaced `Any` on `Router.store / .enricher / .resolver_registry / .ephemeral`. `ephemeral` uses `Mapping` (covariant) for subclass compat.
- [x] Added `FastMCPLike` Protocol in `scaffold.py`; `MCPRunner(server: FastMCPLike, store: ConnectionStore[Any] | None)`.
- [x] Tightened `RouterRegistry._routers` with `_RouterEntry` NamedTuple. Internal `_RegisterableRouter` Protocol documents the duck-typed shape.
- [x] Public `tool_metadata(fn) → ToolMetadata` (frozen, slotted dataclass) wraps the `_a2kit_*` stamps. Exported from top-level `a2kit`.
- [x] Locked `Page[T]` `next_cursor` opaque-str contract in docstring. Left `T` unbounded (Pydantic v2 bound interplay was fragile).
- [x] Hide internal re-exports — reviewed; `BudgetConfig`/`RunnerConfig` are legitimate consumer surface (pyproject [tool.a2kit.runner] config), kept.

Bonus:
- [x] Tightened `ConnectionStoreLike.list_connections() → Sequence[ConnectionInfoLike]` (covariant) so concrete `list[WidgetConn]` returns satisfy the Protocol.
- [x] CHANGELOG entry, README link table updated, version bumped to `0.11.0.dev0`.
- [x] 12 new tests in `test_v11.py`. 618 tests, 100% coverage, ruff + ty clean.

## P1 — formatter robustness

- [ ] **Fix `format_from_annotation` decision-tree gaps** (`formatter.py:128-167`):
  - Bare `dict`, `Mapping[...]`, `TypedDict` → return `"json"`.
  - Unwrap `Awaitable[T]` / `Coroutine[..., T]` before classifying — async tools currently lose precomputation.
- [ ] **`Page[Union[A, B]]`** falls to runtime silently. Add test + log.
- [ ] **`_dump_items` silently drops non-dict/non-BaseModel** (`formatter.py:186-198`).
  - `[1, 2, 3]` → `[]`. Raise instead.
- [ ] **`_flat_pydantic_fields` Union-stripping** handles `Optional[T]` only with one non-None arm. `Optional[Union[A, B]]` falls through.
- [ ] **Drop runtime `_is_uniform_row_list` cross-check** when `_a2kit_format` is set. Trust decoration; let tool bugs surface.

## P1 — verification (Hypothesis)

- [ ] **Property test**: `format_from_annotation(T)` precompute ↔ `toon_or_json(model_dump(instance))` runtime agree for any Pydantic model.
- [ ] **Property test**: `truncate(x)` is structural identity except str clipping; never mutates input.
- [ ] **Property test**: `_coerce_key` accepts {kwargs, tuple, list, NamedTuple, single-string-when-arity-1}; rejects everything else with typed error.

## P2 — asyncio-first

- [ ] **Async connection-store API** (`connections.py:288-315`)
  - Add `load_async`, `save_async`, `list_connections_async` via `anyio.to_thread.run_sync`.
  - Keep sync API intact (sync tools still work).
- [ ] **Switch `_lookup_connection`** (`tools.py:202-208`) to await async variant from `async_wrapper`.
- [ ] **`MCPRunner.run_async()`** for embedding into existing event loop.
- [ ] **`_TRANSPORT_LOCAL` → ContextVar** (`tools.py:81-92`) for consistency with `_RouterContext`.
- [ ] **`EnricherFn` accepts async**: `Callable[..., Exception | Awaitable[Exception]]`. Lets enrichers do async lookups (SSO, etc.).

## P2 — OTel / observability

- [ ] **Record exceptions on the span** — biggest hole. Move `except Exception as exc:` (`tools.py:580, 619`) inside `with span_cm:`, call `span.record_exception(exc)` + `set_status(ERROR)` before enricher runs.
- [ ] **`a2kit.get_tool_logger(name)`** — `LoggerAdapter` injecting `tool.name` + `connection.key`. Auto-correlates with span under OTel `LoggingInstrumentor`.
- [ ] **`tool.result.count` span attribute** when result is list/`Page` (cardinality only — PII safe).
- [ ] **Provider-class string check is fragile** (`_otel.py:64`). Use `isinstance(provider, trace.ProxyTracerProvider)` with `ImportError` fallback.
- [ ] **Spike**: does FastMCP expose MCP JSON-RPC request ID? If yes, stamp as `mcp.request_id` span attribute.

## P3 — internal cleanup (deferred from review)

- [ ] Move `_check_tool_call_contamination` str-typed param set to decoration time (`tools.py:541-544`).
- [ ] `_auto_inject_enabled` cache → `functools.cache`-wrapped fn (`tools.py:790`).
- [ ] `_resolve_store(self, fallback)` helper to dedupe 3x two-tier fallback in scaffold.
- [ ] Tighten `Iterable[ConnectionInfoLike]` → `Sequence` on Protocol (or materialize internally).
- [ ] Document `chain(*enrichers)` first-transforms-wins semantics + lock with short-circuit test.
- [ ] Deprecate tuple/list arms of `_resolve_connection_key` (`tools.py:155-164`); v0.12 delete.
- [ ] MAX_DISPLAYED_CONNECTIONS module constant in `docs.py` (was deferred from v0.10 review).
- [ ] Schema-staleness doc note on `connection_enricher` (decoration-time keys).
- [ ] Lint rules A2K001-A2K013 update for v0.10 patterns.

---

## Top 3 v0.11 bets (from audit)

1. Untangle `errors`/`exceptions` vocabulary (P0 first three items).
2. Replace `Any` on `Router` + `MCPRunner` (P0 typing items).
3. Hypothesis suite for `format_from_annotation` ↔ `toon_or_json` agreement.
