# Tasks — add-internal-spoke

## 1. Auth seam first (generalize before adding a strategy)

- [x] 1.1 Open `AuthTarget` in `packages/auth/spec.py` beyond `Literal["api","mcp"]`
      (open `str`, or add `"internal"`); fix fallout in `registry.for_target`
      typing.
- [x] 1.2 Add `AuthSpec.build_middleware() -> AsgiFactory` to the base contract.
- [x] 1.3 Move `APIKeyAuth`'s existing `build_api_key_middleware(self)` body
      behind `APIKeyAuth.build_middleware()` (no behavior change).
- [x] 1.4 Rewrite `_install_auth_middlewares` (`packages/http/build.py`) to loop
      `for spec in registry.for_target(surface.name): app.add_middleware(...,
      factory=spec.build_middleware())` — delete the `isinstance(APIKeyAuth)`
      branch and the hardcoded `"api"`.
- [x] 1.5 Tests: existing `APIKeyAuth` HTTP behavior unchanged; an unknown-spec
      type now mounts via its `build_middleware()` (no isinstance gate).

## 2. `TokenAuth` strategy (lease-validating)

- [x] 2.1 Add `TokenAuth(AuthSpec)` (`target="internal"`, `header`, `resolve`
      callable) in `packages/auth/`. `build_middleware()` reads the header,
      calls `resolve(token)` **per request**, 401 on miss, publishes the returned
      `Principal` via `request_scope` on hit (mirror `api_key.py`'s publish/reset).
- [x] 2.2 Tests: a token in the live set authenticates → `Principal` with the
      lease scopes reaches `authorize=`; revoking from the set (mid-process) →
      next call 401; no fixed TTL involved.

## 3. Co-resident UDS listener in `serve`

> **Scope correction (build-time finding).** The wired CLI `serve`
> (`cli/_serve.py::register_serve`, Typer) served **MCP-only** over http —
> it never used `build_parent_app`, violating the canonical `serve-topology`
> spec. The spec-compliant multiplex (`mcp/cli.py::build_serve_command`,
> Click) was **orphaned dead code** with a stale docstring. Per the user's
> "serve runs both MCP + API, narrow with an option, UDS in parallel any
> mode" directive and the no-redundancy stance, group 3 now also reconciles
> the two serve commands onto the one wired Typer `serve`.

- [x] 3.1 `build_parent_app` gains `enter_runtime: bool = True` (caller owns
      the single `async with runtime:` when False) and `mcp_options` threading
      so the multiplex carries the serve's `--compact` / `--tools` / code-mode
      knobs instead of silently defaulting them.
- [x] 3.2 Rewrite `register_serve` (`cli/_serve.py`): http path runs the
      `build_parent_app` multiplex (MCP **and** API) under uvicorn; `--select`
      narrows to one surface; stdio stays MCP-only. Existing MCP knobs
      preserved by threading into `mcp_options`.
- [x] 3.3 Add `--internal-uds PATH` to `register_serve`. When set, build the
      runtime **once**, build the spoke app (`build_http_app(runtime,
      auth_target="internal")`), and run the public listener (http parent or
      stdio MCP via `run_stdio_async`) **and** the spoke (uvicorn over a `0600`
      AF_UNIX socket) under one `async with runtime:` + `asyncio.gather`.
- [x] 3.4 Delete the orphaned `packages/mcp/cli.py` (`build_serve_command`) +
      `tests/packages/mcp/test_cli.py` (redundant with the now-canonical
      multiplex serve; removes the stale docstring).
- [x] 3.5 Tests: `build_parent_app(enter_runtime=False)` does not enter the
      runtime in its lifespan; `mcp_options` reach the MCP build; an e2e
      multi-listener serve answers a verb over the UDS (validation + audit +
      `TokenAuth` principal) writing through the **same** `SINGLETON` store as
      a TCP call; public surfaces unchanged; no-token UDS connection rejected.

## 4. Spoke client

- [x] 4.1 Add `a2kit.spoke.client(socket_path, token)` (thin wrapper over a UDS
      transport) exposing `invoke(canonical_name, **kwargs)`. No fastmcp/httpx
      internals leak to callers.
- [x] 4.2 Test: the client's projected catalog matches the API surface's
      canonical names (no second catalog); an `invoke` round-trips over the UDS.

## 5. Optional hardening (flag, do not block)

- [~] 5.1 Peer-cred check (`SO_PEERCRED` / `getpeereid`) on accept —
      **deferred** (recorded in ADR 0029 "Deferred"). Awkward to do
      cleanly under uvicorn and marginal once `0600` + the lease token are
      in place (token is the primary control, the `0600` socket the
      secondary). Revisit only if a shared-host threat model demands it.

## 6. Docs + gates

- [x] 6.1 ADR under `docs/adr/` recording the spoke (transport=UDS, lease auth,
      shared-runtime/SINGLETON store, the write-serialization caveat) and the
      explicit deferral of the surface-composition framework.
- [x] 6.2 Supersede / delete `docs/dev/integration-surface-plan.md` (it still
      describes the rejected trust-by-channel no-auth design).
- [x] 6.3 Run a2kit lint / type / test gates. (ruff clean; `ty check src/`
      clean; `a2kit lint static src/ tests/ examples/` exit 0; full suite
      1592 passed / 50 skipped, coverage 90.21%. The 28 `ty tests/` errors
      are the pre-existing tolerated baseline — none in this change's files.)
