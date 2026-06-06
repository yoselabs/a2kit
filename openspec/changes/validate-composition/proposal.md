## Why

A tool's **canonical name is the audit-log/call-journal key** (ADR 0028
decision 6). If two verbs resolve to the same canonical name, every
downstream consumer of that key — the call journal, operator dashboards,
authorization rules keyed by name — silently becomes ambiguous. So the
name MUST be unique **globally** (not per-surface): a CLI-only `foo` and
an MCP-only `foo` still collide in the one shared audit log, even though
they never share a network namespace.

Today this is enforced **only** inside `runtime.build()` — and even there
only for `expose=` surface names (`_validate_descriptor_expose`,
`runtime.py:421`), not for canonical-name uniqueness at all. Two
problems:

1. **No name-uniqueness backstop exists.** Nothing resolves the canonical
   name for every verb and asserts global uniqueness. A dynamic
   collision (names a static linter cannot see) sails through to a live,
   ambiguous audit log.
2. **Validation is build-gated (friction #4, list-half).** What
   validation does exist runs only when you pay for a full
   `build()` — sealing a fresh container, re-materializing descriptors,
   composing the surface registry. `app.tools()` returns descriptors with
   **no** validation (`app.py:472`). A unit test that wants to assert
   "this App composes cleanly" must either stand up a full runtime or get
   nothing.

ADR 0028's answer is **"complain early, complain often"** over **one**
`resolve_canonical_name` resolver, in two layers:

- **Lint (layer 1, primary — "complain often").** A static rule resolves
  literal slugs + `canonical_name_override`s across the codebase and
  flags duplicate canonical names *before the app runs*. This layer is
  delivered by the orthogonal `ruff-compatible-lint-codes` change and is
  explicitly **out of scope here**.
- **Runtime (layer 2, backstop — "complain early, loud").** A standalone
  `validate_composition(app)` resolves the surfaces matrix and the
  canonical name for every verb, asserts global uniqueness, and fails
  loud with the offending pair — *without* a full build, so unit tests
  can call it directly. It catches the dynamic-name collisions the linter
  cannot resolve statically.

This change delivers that runtime backstop. It is the
list-half complement to `fix-http-visibility-leak` (the leak-half of
friction #4) and is **additive, non-breaking** (Wave 3).

## What Changes

Add a standalone `validate_composition(app)` function that, **without a
full surface build**:

- resolves the `surfaces`/`expose` matrix for every verb (the same
  surface-name check `build()` already performs, now available offline);
- resolves the **canonical name** for every verb through the one shared
  `resolve_canonical_name` resolver (auto-derived `slug_leaf`,
  app-level bare `leaf`, or a verbatim `canonical_name_override`);
- asserts **global** canonical-name uniqueness across all routers and
  app-level verbs — independent of which surface each verb appears on;
- **fails loud** on the first collision with both offending verbs named
  (router/slug + leaf + resolved name), so the diagnostic points straight
  at the fix;
- is callable directly in unit tests against a compose-phase `App` (no
  container seal, no descriptor re-materialization, no transport build).

`build()` continues to be the production gate; this change makes the same
guarantees reachable earlier and standalone. (Whether `build()` calls
`validate_composition` internally is captured as an optional MODIFIED
requirement on `core-composition` — see Capabilities.)

## Capabilities

### Added Capabilities

- `validate-composition` — the standalone `validate_composition(app)`
  validator contract: resolve the surfaces matrix + the canonical name
  for every verb, assert global canonical-name uniqueness, fail loud with
  the offending pair, unit-testable with no full build.

### Modified Capabilities

- `core-composition` — `build()` invokes `validate_composition` as part
  of its finalize step, so the runtime backstop runs on every production
  build (not only when a test calls the validator directly). Same
  guarantee, two entry points.

## Impact

- **Additive, non-breaking.** A new public function plus a build-time
  call to it. No existing surface, name, or descriptor shape changes. An
  App that already composes uniquely sees no behavior change; an App with
  a latent duplicate name now fails loud at `build()` / on the validator
  call instead of producing an ambiguous audit log.
- **Relationship to the lint layer.** This is **layer 2** of the
  two-layer model. Layer 1 (the static dup-name lint rule with a
  ruff-compatible code) lives in the separate `ruff-compatible-lint-codes`
  change. Both layers call the **same** `resolve_canonical_name`
  function, so they cannot disagree on what a name resolves to. The lint
  catches literal/static collisions early in the editor/CI; this runtime
  backstop catches dynamic names the linter cannot see.
- Affected code (informational; this change is artifact-authoring only):
  a new `validate_composition` entry point and a shared
  `resolve_canonical_name` resolver, called from both the validator and
  `runtime.build()`.

## Non-goals

- **The static lint rule itself.** The dup-name lint (layer 1) and its
  ruff-compatible code live entirely in the orthogonal
  `ruff-compatible-lint-codes` change. This change only provides — and
  shares — the `resolve_canonical_name` resolver they both consume.
- **The flat canonical-name scheme / the rename.** `slug_leaf`
  canonicalization and `canonical_name_override` are defined by
  `native-tree-homomorphism` (Wave 2). This change *validates uniqueness
  of* whatever the resolver produces; it does not define the resolution
  rule.
- **The HTTP visibility leak (friction #4, leak-half).** Fixed
  separately in `fix-http-visibility-leak`.
- **Per-surface name scoping.** Uniqueness is global by design (the audit
  key is global); this change does not add a per-surface relaxation.
