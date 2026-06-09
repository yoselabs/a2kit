# Tasks — fix-http-visibility-leak

BDD-first: the leak gets a failing test that proves a CLI-only verb is
reachable over HTTP today, before the fix (TDD red → green).

## 1. Prove the leak (RED)

- [x] 1.1 Add a test: build an App with a `visibility="cli"` projection
      verb, assemble `build_http_app(runtime)`, assert there is **no**
      `POST /api/<name>` route for it (route absent / 404). Confirm it
      FAILS against current code (the route exists today — the leak).
      → `test_cli_only_verb_not_mounted_on_http`. Confirmed RED
      (`/trust_vault` was mounted today).
- [x] 1.2 Add a parallel test for `visibility="hidden"` (also must be
      absent from HTTP). Confirm it fails today.
      → `test_hidden_verb_not_mounted_on_http`. Confirmed RED.
      Plus `test_http_no_di_override_for_non_all_visibility` for the DI
      half of the leak — proven RED only with *concrete* annotations
      (PEP 563 string annotations mask it), so its fixture lives in a
      dedicated no-`__future__` module `tests/packages/http/_vault_fixture.py`
      to reproduce a real downstream app faithfully.
- [x] 1.3 Add a parity test: same App, assert the set of HTTP-mounted
      tool names equals the set of MCP-registered tool names for the
      network-visible verbs (one rule, two surfaces).
      → `test_http_and_mcp_apply_same_visibility_rule` (builds both
      `build_http_app` and `build_mcp_server`, asserts both expose exactly
      `public_op` and neither exposes `trust_vault`/`secret_op`).

## 2. Fix the filter (GREEN)

- [x] 2.1 `packages/http/build.py` route loop: after the
      `"api" not in desc.expose` guard, also `continue` when the resolved
      visibility is not `"all"`. Use the same accessor MCP uses
      (`desc._meta.extras.visibility or "all"`), so the two surfaces share
      one rule.
- [x] 2.2 `packages/http/build.py` DI override loop: apply the
      identical visibility guard so no `dependency_overrides` entry is
      registered for a non-`"all"` verb (no dangling resolver for an
      unmounted route).
- [x] 2.3 Keep the guard expressed once / readably.
      → Single module-level predicate `_http_mountable(desc)` (expose +
      visibility) called by both loops, so they cannot drift apart.

## 3. Verify (GREEN)

- [x] 3.1 New tests from §1 now pass.
- [x] 3.2 Existing http-surface tests stay green (visible verbs still
      mount; DI still resolves for them) — 54 http tests pass.
- [x] 3.3 Full suite green, output pristine
      (1522 passed, 50 skipped, 90.42% coverage).

## 4. Close out

- [x] 4.1 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files. (Repo-wide `ty` has 15 pre-existing `tests/`
      diagnostics from the in-flight `refound-ldd-on-stdlib-logging`
      change — none in files touched here; pre-commit `ty` scans `src/`.)
- [x] 4.2 Forward-compat seam: under ADR 0028 `_http_mountable` becomes
      "honor the `surfaces` matrix"; the rule chosen here (network
      surfaces drop non-`all`) is the same decision in today's vocabulary.
