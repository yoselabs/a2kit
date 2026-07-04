## 1. Root `/health` on the multiplex parent (BDD-first)

- [x] 1.1 Write failing scenarios first (per `feedback_bdd_first`): against a
      parent built from an MCP-only runtime, `GET /health` → 200
      `{"status": "ok"}`; same for an api-only runtime and a both-surfaces
      runtime. Use the in-process test client (`in-process-test-client`).
- [x] 1.2 Add a static `Route("/health", _live, methods=["GET"])` to
      `build_parent_app`'s `routes=[...]` (`packages/serve.py`), handler
      returns `JSONResponse({"status": "ok"})`, 200 — no runtime/DI access.
      (Also filtered `_mount_paths` test helper to `Mount`s so the liveness
      route does not perturb the exact-equality mount-shape assertions.)
- [x] 1.3 Scenario: `/health` answers even with a wedged DI graph — a runtime
      whose provider resolution would raise still returns 200 on `/health`
      (proves the handler touches no DI).
- [x] 1.4 Scenario: auth-free by construction — with an auth strategy
      configured on a surface (`APIKeyAuth` on `api`), `GET /health` (parent
      root) returns 200 with **no** credentials while `/api/*` 401s.

## 2. Guarantee across surface selections

- [x] 2.1 Scenario: MCP-only serve exposes `/health` (regression lock for the
      exact gap the wish reported).
- [x] 2.2 Confirm the existing `/api/health` on the FastAPI sub-app is
      unchanged (back-compat) — a both-surfaces serve exposes both `/health`
      and `/api/health`.
- [x] 2.3 Confirm the zero-surface `ValueError` path in `build_parent_app` is
      unchanged (existing `test_build_parent_app_requires_a_surface` covers it).

## 3. Optional additive — `custom_route` on the bare MCP app

- [x] 3.1 **Decided: NO.** a2web serves through the parent, so the parent-root
      route unblocks it; a `custom_route` in `build_mcp_server` is uncalled-for
      surface today and becomes the consumer's own concern under the refounding
      (ADR 0032). Deferred — not implemented.
- [~] 3.2 Skipped (follows from 3.1 = No).

## 4. Docs + validation

- [x] 4.1 Note the transport-native liveness route in `OPERATIONAL_CONTRACTS.md`
      alongside the `_meta.*` readiness namespace (liveness vs readiness split).
- [x] 4.2 `CHANGELOG.md` entry (additive; new minor).
- [x] 4.3 `openspec validate --strict` green; `make test` green.

## Out of scope (tracked, not done here)

- The `APIKeyAuth` non-exemption of `/api/health` (`auth/api_key.py`) — a
  separate latent bug; the new root route does not depend on fixing it.
- a2web-side adoption (Dockerfile `HEALTHCHECK`, retiring the escape-hatch
  interim) — lands in a2web's `deployable-container-ci`.
