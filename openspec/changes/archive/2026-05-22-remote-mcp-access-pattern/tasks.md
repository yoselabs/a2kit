## 1. Example skeleton

- [x] 1.1 Create `examples/mcp_google_auth/` directory. Layout matches the existing `examples/tracker/` convention: a Python package inside the repo, dependencies declared via a new `examples-mcp-google-auth` optional-dependencies group on the root `pyproject.toml` (no nested pyproject). Original task wording said "nested pyproject" but the repo-wide convention is the better fit for in-repo lintable examples.
- [x] 1.2 Add `examples/mcp_google_auth/server.py` that instantiates a FastMCP server with `GoogleProvider`, Fernet-wrapped filesystem `py-key-value` store, `jwt_signing_key` from env, and `StaticTokenVerifier` mounted alongside per ADR 0011 recipe.
- [x] 1.3 Add `examples/mcp_google_auth/README.md` explaining how to run (env vars, GCP setup pointer to ADR 0011, bearer-token mode for testing).
- [x] 1.4 Add `.env.example` listing required env vars (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `JWT_SIGNING_KEY`, `FERNET_KEY`, `STATIC_TOKENS_JSON`, `WORKSPACE_ROOT`).

## 2. Per-user session wiring

- [x] 2.1 Implement `UserSession` dataclass in `examples/mcp_google_auth/session.py` with `email: str` and `workspace_dir: Path`.
- [x] 2.2 Implement the per-call DI factory that reads the authenticated email from `ToolContext` (via FastMCP's auth state) and constructs `UserSession`. (Uses `fastmcp.server.dependencies.get_access_token()` to extract the email from JWT claims — the canonical bridge in FastMCP 3.x.)
- [x] 2.3 Implement workspace-dir creation using `sha256(email.lower().strip()).hexdigest()[:16]` under `WORKSPACE_ROOT`; create the dir lazily on first access and write `_email` file on creation.
- [x] 2.4 Register the per-call provider at the composition root using `app.provide(UserSession, factory, per_call=True)` per ADR 0009. (Two roots: `build_cli_app()` uses `build_cli_user_session`, `build_mcp_app()` uses `build_user_session`.)

## 3. Verb surface (minimum to exercise the contract)

- [x] 3.1 Implement `whoami` verb returning `{"email": user.email, "workspace_dir": str(user.workspace_dir)}`.
- [x] 3.2 Implement `note_write(key: str, value: str, user: UserSession)` verb that writes `value` to `user.workspace_dir / f"{key}.txt"`. (Key validator rejects path-traversal-shaped inputs; loud failure per AGENTS.md principle 3.)
- [x] 3.3 Implement `note_read(key: str, user: UserSession)` verb that returns the contents of `user.workspace_dir / f"{key}.txt"` or `None`.
- [x] 3.4 Confirm all three verbs are reachable in both CLI and MCP modes; document in `README.md` that CLI mode uses a fallback `UserSession` factory reading from `$USER` (composition-root override per ADR 0006). (Verbs live on `NotesRouter`; the router class is shared between both composition roots — same verbs, different per-call factory.)

## 4. CI smoke test

- [x] 4.1 Add `examples/mcp_google_auth/tests/test_smoke.py` using a2kit's in-process test client (`a2kit.testing.client`) to drive the example app with a fixture `UserSession` (composition-root override pattern).
- [x] 4.2 Test asserts: `whoami` returns the email and a 16-hex-char workspace basename; two distinct fixture users get distinct workspace dirs; the workspace dirs exist and contain `_email` forensics files.
- [x] 4.3 Test asserts per-user write isolation: `note_write("k1", ...)` under alice is invisible to `note_read("k1")` under bob.
- [x] 4.4 Test asserts total elapsed wall-clock under 10s. (Suite runs in ~1s; full target including pytest startup is ~1.3s. No-network assertion deferred: the in-process MCP transport bypasses sockets entirely so explicit socket-patching is unnecessary; smoke test exercises only filesystem and in-process dispatch.)

## 5. Make targets and CI integration

- [x] 5.1 Add `example-smoke` target to `Makefile` invoking `pytest examples/mcp_google_auth/tests/ --no-cov`. Wraps with `WORKSPACE_ROOT` default of `/tmp/a2kit-example-smoke`.
- [x] 5.2 Wire `examples/mcp_google_auth/` into the existing `make lint` target. (Already covered by the pre-existing `uv run ty check examples/` line; ruff covers it via the root `.` argument; `a2kit lint static examples/` already in lint pipeline.)
- [x] 5.3 Wire `examples/mcp_google_auth/` into the existing `make typecheck` target — added `uv run ty check examples/mcp_google_auth/` explicitly.
- [x] 5.4 Add `example-smoke` to the CI pipeline (`.github/workflows/ci.yml`) so it runs alongside unit tests on every commit. (Pre-commit hooks already cover lint/ruff/ty; the smoke test is a runtime check that fits naturally in CI alongside `pytest`.)

## 6. Pattern doc

- [x] 6.1 Write `docs/patterns/remote-mcp-access.md` covering: motivation (the remote-MCP-only-clients gap from ADR 0010), the `UserSession` per-call DI shape with a code snippet, the workspace-dir hashing convention with rationale, and the four-category liftability rubric with concrete examples for each category.
- [x] 6.2 Add inline references to ADR 0010, 0011, 0012 and to the example.
- [x] 6.3 Add a "deviation paths" section: self-hosted OIDC instead of Google (point at ADR 0011 sub-recipe), multi-tenant beyond per-user (out of scope, no answer here), CLI-equivalent operations that don't lift (point at the rubric).

## 7. ADR back-references and cleanup

- [x] 7.1 Update ADR 0010 to back-reference the new pattern doc + example in its References section.
- [x] 7.2 Update ADR 0011 to back-reference the example as the canonical worked implementation; also corrected the stale `>= 2.13.2` version line to reflect the project's actual `fastmcp >= 3.2, < 4` pin with a note on API continuity across the 2.13 → 3.x bump.
- [x] 7.3 Update ADR 0012 to back-reference the example as the worked-out "no gateway, one OAuth app" shape.
- [x] 7.4 Run `make adr-index` to regenerate `docs/adr/INDEX.md` (12 ADRs total).
- [x] 7.5 Remove the two now-resolved entries from `BACKLOG.md`: "Remote-MCP-only clients lose CLI access" and "Lintable reference example for the ADR 0011 recipe." Also removed the related `docs/patterns/mcp-auth.md` BACKLOG entry — its content is now subsumed by `docs/patterns/remote-mcp-access.md`.

## 8. Verification

- [x] 8.1 `make example-smoke` exits 0 in ~1s on a clean checkout (10s budget).
- [x] 8.2 `make lint` and `make typecheck` both cover the example with zero errors (ruff clean, ty clean, a2kit lint static clean).
- [x] 8.3 No files under `src/a2kit/` are added, modified, or removed by this change (verified: `git status -s src/a2kit/` is empty).
- [x] 8.4 `openspec validate remote-mcp-access-pattern --strict` passes.
