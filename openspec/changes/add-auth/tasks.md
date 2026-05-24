# Tasks — add-auth

> Tier 1, depends on `propagate-principal-and-authorize`,
> `add-substrate-dep-class`, `bridge-container-fastapi-depends`,
> `add-surface-protocol-additive`, `remove-substrate-literal`
> (all landed). BDD-first: write the Gherkin spec before any
> production code.

## 1. Package skeleton + cold-start gates

- [ ] 1.1 New package `src/a2kit/packages/auth/` with PEP 562 `__init__.py` facade. Re-exports `GoogleAuth`, `APIKeyAuth`, `JwtAuth`, `AuthSpec` lazily.
- [ ] 1.2 `src/a2kit/packages/auth/spec.py` — `AuthSpec` base + targeting metadata (which surface a spec applies to).
- [ ] 1.3 BDD: `tests/packages/auth/test_cold_start.py` — `import a2kit` does not load `a2kit.packages.auth`; `import a2kit.packages.auth` does not load `fastmcp.server.auth.providers.*`, `python-jose`, `cryptography`, `httpx`.

## 2. `App.auth(spec)` registration surface

- [ ] 2.1 BDD: `tests/test_app_auth_registry.py` — `app.auth(GoogleAuth(...))` accumulates; multiple calls append; the registry is iterable; order is preserved.
- [ ] 2.2 `App.auth(spec: AuthSpec) -> None` method on `a2kit.App`. Backed by an internal `AppAuthRegistry` accumulator (mirrors `mcp_surface` / `api_surface` pattern).
- [ ] 2.3 `AppRuntime.auth_registry` field. Populated by `build()` from the source App.

## 3. `APIKeyAuth` — primary HTTP path

- [ ] 3.1 BDD: `tests/packages/auth/test_api_key.py` — request with valid `X-API-Key` resolves to expected `Principal`; missing header → 401; bad key → 401; valid key + `authorize=` passes → 200; valid key + denying `authorize=` → 403.
- [ ] 3.2 `src/a2kit/packages/auth/api_key.py` — `APIKeyAuth` dataclass: `keys: Iterable[ApiKey] | Callable[[], Iterable[ApiKey]]`, `header: str = "X-API-Key"`.
- [ ] 3.3 `ApiKey` dataclass: `value: str`, `subject: str`, `scopes: frozenset[str] = frozenset()`.
- [ ] 3.4 Middleware factory: returns an ASGI middleware that reads the header, looks up the key, synthesises a `Principal`, sets `_a2kit_request_principal` for the request lifetime, and resets on exit. 401 JSON envelope on failure.
- [ ] 3.5 `build_http_app` consults `runtime.auth_registry` and mounts `APIKeyAuth` middleware when present. No middleware when no `APIKeyAuth` registration exists (cold-start invariant).

## 4. `JwtAuth` — secondary HTTP path

- [ ] 4.1 BDD: `tests/packages/auth/test_jwt.py` — valid JWT (signed by JWKS, correct aud/iss/exp) resolves to `Principal`; bad signature → 401; expired token → 401; wrong audience → 401; mixed `APIKeyAuth + JwtAuth` registration: API-key header wins when present, JWT path runs when not.
- [ ] 4.2 `src/a2kit/packages/auth/jwt.py` — `JwtAuth` dataclass: `jwks_url: str`, `audience: str`, `issuer: str`, optional `algorithms: tuple[str, ...] = ("RS256",)`.
- [ ] 4.3 JWKS fetcher with TTL caching (default 10 min). Lazy `httpx` import inside the fetcher.
- [ ] 4.4 Middleware factory parallels `APIKeyAuth`. `Principal.claims` carries the full decoded payload; `scopes` parsed from `scope` (space-separated) or `scp` (array) claim.

## 5. `GoogleAuth` — MCP OAuth path

- [ ] 5.1 BDD: `tests/packages/auth/test_google.py` — `GoogleAuth(...).to_fastmcp_provider()` returns a configured `GoogleProvider`; `build_mcp_server` passes the provider as `auth=` to `FastMCP(...)`; the existing `PrincipalMiddleware` lifts `Context.access_token` into `_a2kit_request_principal` (already tested; this is a smoke assertion).
- [ ] 5.2 `src/a2kit/packages/auth/google.py` — `GoogleAuth` dataclass with the fields the underlying `GoogleProvider` needs (client_id, client_secret, base_url, …). Lazy import of `fastmcp.server.auth.providers.google` inside `to_fastmcp_provider`.
- [ ] 5.3 `build_mcp_server` reads `runtime.auth_registry`, finds the first MCP-targeting spec (if any), passes its `to_fastmcp_provider()` result as `auth=` to `FastMCP`.

## 6. `auth.testing` — test seam

- [ ] 6.1 BDD: `tests/packages/auth/test_testing_seam.py` — `authenticated_as(principal)` context manager binds the contextvar inside and resets on exit (success + exception paths).
- [ ] 6.2 `src/a2kit/packages/auth/testing.py` — `make_principal(...)` factory; `authenticated_as(principal)` context manager.
- [ ] 6.3 Re-export from `a2kit.testing` so authors find them in the standard test-helper namespace.

## 7. End-to-end integration

- [ ] 7.1 BDD: `tests/test_auth_end_to_end.py` — App with one `@a2kit.read(authorize=admin_only)` tool + `APIKeyAuth(keys=[ApiKey("k1", "admin", {"admin"})])`. POST `/api/<tool>` with valid admin key returns 200; with non-admin key returns 403; with no key returns 401.
- [ ] 7.2 BDD: same App on MCP with mocked `Context.principal` — admin scope allows, non-admin denies, no principal denies.

## 8. Spec deltas

- [ ] 8.1 New spec `openspec/specs/auth-spec/spec.md`. Wrapper surface (`GoogleAuth`/`APIKeyAuth`/`JwtAuth`), `App.auth(...)`, cold-start invariants.
- [ ] 8.2 New spec `openspec/specs/tool-authorization/spec.md`. Per-tool `authorize=` enforcement uniformity, error envelopes, test seam. (References `principal-propagation` for `Principal` ownership.)
- [ ] 8.3 Modify `openspec/specs/multi-surface-authoring/spec.md`: note `authorize=` runtime enforcement is now live (kwarg was reserved by `add-multi-surface`; enforcement landed in `propagate-principal-and-authorize`; identity providers landed here).
- [ ] 8.4 Modify `openspec/specs/http-surface/spec.md`: API-key + JWT middleware mounted by `build_http_app` when registry contains matching spec; no middleware when empty.

## 9. Documentation

- [ ] 9.1 README: short "Authentication" section pointing at the three wrappers + the `authorize=` kwarg.
- [ ] 9.2 No new ADR — design.md in this change captures the trade-offs.

## 10. Final gates

- [ ] 10.1 `make lint` / `make test` / `make component-map --check` all green.
- [ ] 10.2 Cold-start budget: `import a2kit` benchmark unchanged.
- [ ] 10.3 Dependency footprint: `python-jose` (or equivalent) + `httpx` added as an optional dep group `auth` in `pyproject.toml`; `import a2kit` works without the group installed (lazy imports raise actionable errors only when an auth spec is constructed).
