# Tasks — fix-http-visibility-leak

BDD-first: the leak gets a failing test that proves a CLI-only verb is
reachable over HTTP today, before the fix (TDD red → green).

## 1. Prove the leak (RED)

- [ ] 1.1 Add a test: build an App with a `visibility="cli"` projection
      verb, assemble `build_http_app(runtime)`, assert there is **no**
      `POST /api/<name>` route for it (route absent / 404). Confirm it
      FAILS against current code (the route exists today — the leak).
- [ ] 1.2 Add a parallel test for `visibility="hidden"` (also must be
      absent from HTTP). Confirm it fails today.
- [ ] 1.3 Add a parity test: same App, assert the set of HTTP-mounted
      tool names equals the set of MCP-registered tool names for the
      network-visible verbs (one rule, two surfaces).

## 2. Fix the filter (GREEN)

- [ ] 2.1 `packages/http/build.py` route loop (~`:83`): after the
      `"api" not in desc.expose` guard, also `continue` when the resolved
      visibility is not `"all"`. Use the same accessor MCP uses
      (`desc._meta.extras.visibility or "all"`), so the two surfaces share
      one rule.
- [ ] 2.2 `packages/http/build.py` DI override loop (~`:331`): apply the
      identical visibility guard so no `dependency_overrides` entry is
      registered for a non-`"all"` verb (no dangling resolver for an
      unmounted route).
- [ ] 2.3 Keep the guard expressed once / readably (small helper or
      shared predicate) so route-loop and DI-loop cannot drift apart.

## 3. Verify (GREEN)

- [ ] 3.1 New tests from §1 now pass.
- [ ] 3.2 Existing http-surface tests stay green (visible verbs still
      mount; DI still resolves for them).
- [ ] 3.3 Full suite green, output pristine.

## 4. Close out

- [ ] 4.1 lint / typecheck / markdown gates green.
- [ ] 4.2 Note the forward-compat seam: under ADR 0028 this predicate
      becomes "honor the `surfaces` matrix"; the rule chosen here
      (network surfaces drop non-`all`) is the same decision expressed in
      today's vocabulary.
