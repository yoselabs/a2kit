# Tasks — ctx-surface-identity

BDD-first / TDD red → green. Every behaviour gets a failing test that
proves the surface is invisible today, before the field exists. Depends on
`refound-ldd-on-stdlib-logging` (provides `_CallScope` / `bind_call_scope`
/ `_CallScopeFilter` / `CallRecord`); these tasks EXTEND those, never
redefine them.

## 0. Confirm the gap (RED — baseline)

- [ ] 0.1 Add a test that dispatches the same tool over MCP, `/api`, and
      CLI and asserts each call can report which surface invoked it.
      Confirm it FAILS today (no `surface` on the scope; `current_surface`
      does not exist). → `test_surface_identity_absent_today`.

## 1. Extend the per-call scope (RED → GREEN)

- [ ] 1.1 Test: `_CallScope` carries `surface: str | None` and
      `surface_client_id: str | None`, both defaulting `None`. RED first
      (fields absent). → `test_call_scope_has_surface_fields`.
- [ ] 1.2 Test: `bind_call_scope(..., surface="mcp",
      surface_client_id="c1")` publishes a scope whose `surface == "mcp"`
      and `surface_client_id == "c1"`; calling without them yields `None`
      for both (backward-compat). → `test_bind_call_scope_stamps_surface`.
- [ ] 1.3 GREEN: add the two optional fields to `_CallScope` and the two
      optional kwargs to `bind_call_scope` (`src/a2kit/packages/log/scope.py`).

## 2. Read accessor (RED → GREEN)

- [ ] 2.1 Test: `a2kit.log.current_surface()` returns the active scope's
      `surface` inside a dispatch and `None` outside any dispatch (never
      raises). Companion `current_surface_client_id()` likewise. RED first.
      → `test_current_surface_accessor`.
- [ ] 2.2 GREEN: add `current_surface()` / `current_surface_client_id()`
      reading `_active_scope()` and returning `None` when no scope.

## 3. Stamp at the dispatch boundary (RED → GREEN)

- [ ] 3.1 Test: a tool dispatched via the real MCP transport
      (`fastmcp.Client(transport=build_mcp_server(app))`) reads
      `current_surface() == "mcp"` from its body. RED first.
      → `test_mcp_dispatch_stamps_surface`.
- [ ] 3.2 Test: a tool dispatched via the HTTP surface
      (`build_http_app` + TestClient POST `/api/<name>`) reads
      `current_surface() == "api"`. → `test_http_dispatch_stamps_surface`.
- [ ] 3.3 Test: a tool dispatched via the CLI runtime reads
      `current_surface() == "cli"`. → `test_cli_dispatch_stamps_surface`.
- [ ] 3.4 Test: when the MCP ctx exposes a `client_id`, it lands on the
      scope as `surface_client_id`; when no client id is available the
      field is `None` (no crash). → `test_surface_client_id_optional`.
- [ ] 3.5 GREEN: `CallScopeStage` (`src/a2kit/packages/dispatch/stages.py`)
      resolves the dispatching surface's identity and passes
      `surface=` / `surface_client_id=` into `bind_call_scope`. The
      surface name comes from the dispatching surface (`Surface.name`;
      `"cli"` for the CLI runtime), NOT from sniffing the ctx type.

## 4. Surface rides the records (RED → GREEN)

- [ ] 4.1 Test: every `LogRecord` handled by the `a2kit` logger inside a
      dispatch carries a `surface` attribute equal to the active scope's
      surface; outside any dispatch it is `None`.
      → `test_log_record_carries_surface`.
- [ ] 4.2 Test: with the call-log enabled, the durable call-record /
      access-log row carries the `surface` field for the invoking surface.
      → `test_call_record_carries_surface`.
- [ ] 4.3 GREEN: extend `_CallScopeFilter` to inject `surface` onto each
      record; ensure the `CallRecord` / access-log row includes it (rides
      the existing refound record — no new record concept).

## 5. Isolation & absence (GREEN)

- [ ] 5.1 Test: under concurrent `asyncio.gather`, two calls arriving on
      different surfaces each read only their own `surface` (per-call
      isolation via the existing `request_scope` copy-on-write).
      → `test_concurrent_surfaces_isolated`.
- [ ] 5.2 Test: a nested dispatch (tool A on `api` invokes tool B via the
      in-process client) — B's scope reports its own dispatch surface,
      and A's reads restore after B returns.
      → `test_nested_dispatch_surface_shadows_and_restores`.
- [ ] 5.3 Test: a dispatch where no surface is resolvable yields
      `current_surface() is None` and does NOT raise.
      → `test_unresolvable_surface_is_none`.

## 6. Verify & close out

- [ ] 6.1 All new tests from §0–§5 pass.
- [ ] 6.2 Existing scope / call-log / mcp-context tests stay green
      (additive fields do not perturb today's behaviour).
- [ ] 6.3 Full suite green, output pristine.
- [ ] 6.4 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files.
- [ ] 6.5 Confirm forward-compat seam: under Wave 1 (`cli-as-surface`) the
      identity each surface stamps is exactly its `Surface.name`; this
      change defines the contract the unified surfaces satisfy.
