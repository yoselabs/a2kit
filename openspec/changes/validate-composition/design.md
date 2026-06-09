# Design — validate-composition

## Context

ADR 0028 (decision 6) makes the canonical name the **call-journal/audit
key** and mandates two-layer, **global** uniqueness enforcement over one
resolver. `docs/SURFACE_ARCHITECTURE.md` §5 ("Uniqueness — two layers
over one resolver") and §7 (Wave 3) scope this change as the **runtime
backstop**: a standalone `validate_composition(app)` that resolves the
surfaces matrix + canonical names and asserts global uniqueness, callable
in unit tests with no full build.

Today: `runtime.build()` runs `_validate_descriptor_expose` (surface-name
check only) — there is **no** canonical-name uniqueness check anywhere,
and `app.tools()` runs no validation at all. This change closes both
gaps for the runtime layer.

## Two layers over one resolver

```
  resolve_canonical_name(verb)            ← THE single resolver (ADR 0028 §5 precedence)
        │
        ├── LINT  (layer 1, primary — "complain often")
        │     static rule; resolves literal slugs + canonical_name_overrides;
        │     flags dup names before the app runs; ruff-compatible code.
        │     >>> Lives in the SEPARATE `ruff-compatible-lint-codes` change. <<<
        │
        └── RUNTIME (layer 2, backstop — "complain early, loud")  ← THIS CHANGE
              validate_composition(app): resolves every verb, asserts GLOBAL
              uniqueness, fails loud w/ the offending pair. Standalone (tests)
              + invoked by build(). Catches dynamic names lint can't see.
```

The two layers MUST consume the **same** `resolve_canonical_name`
function. If each had its own copy of the precedence
(`canonical_name_override` verbatim → `slug_leaf` → bare `leaf`), they
could drift and disagree on what a name resolves to — defeating the point
of a backstop. One function, two callers.

### Why a runtime backstop at all, if lint runs first?

The lint resolves **literal** slugs and overrides statically. A verb
whose canonical name is computed dynamically (a value the linter cannot
evaluate without running the program) is invisible to layer 1. Layer 2
runs over the live composed App, so it sees the actual resolved name.
ADR 0028: "catches dynamic names the linter cannot resolve statically."
Conversely, layer 1 catches mistakes before the program is ever run
("complain often"). They are complementary, not redundant.

## Why uniqueness is global, not per-surface

The naive intuition is per-surface scoping: a CLI-only `foo` and an
MCP-only `foo` never share a transport namespace, so why collide?

Because the canonical name is **not** a per-surface identifier — it is the
**one shared audit/call-journal key** (ADR 0028 decision 6). The call
journal records "verb `foo` was invoked" with no surface qualifier in the
key. If two distinct verbs both log as `foo`, every downstream consumer of
that key — operator dashboards, authorization rules keyed by name,
forensic replay — becomes ambiguous, regardless of which surface each verb
was reachable on. So uniqueness is asserted across the **global** set of
all app-level and router verbs, independent of the `surfaces` matrix.

(MCP is also the one *flat* transport namespace, so MCP-level collisions
are a transport bug too — but the global rule is justified by the audit
key alone, which is why it holds even for two verbs that never co-exist on
any single surface.)

## No full build

`validate_composition(app)` deliberately avoids the cost and side effects
of `build()`:

- **No container seal** — the App stays a reusable, mutable builder
  (`app.container()` remains unsealed), so a test can validate then keep
  composing.
- **No descriptor re-materialization** — wire/lazy fields (populated only
  against a sealed runtime container) are not needed to resolve names or
  the surfaces matrix.
- **No transport construction** — no FastAPI / FastMCP / Typer object is
  built; cold-start and import discipline are preserved.

This is what makes it unit-testable: a test asserts "this App composes
cleanly" in isolation, with no runtime, no transports, no async lifecycle.

## build() integration (core-composition MODIFIED)

`build()` invokes the same backstop during finalize so production builds
always run layer 2 (a test author might forget to call the validator; a
production serve never skips `build()`). Same resolver, same global
uniqueness assertion, same loud failure with the offending pair — two
entry points, one guarantee. This is the optional `core-composition`
MODIFIED requirement; it reads cleanly as an addition to the existing
"App composition uses three named verbs" requirement's description of the
finisher's `build(app)` step.

## Scope boundaries

- The **lint rule** (layer 1) and its ruff-compatible code: out of scope;
  `ruff-compatible-lint-codes`. This change only provides/shares the
  resolver.
- The **`slug_leaf` scheme + `canonical_name_override`**: defined by
  `native-tree-homomorphism` (Wave 2). This change validates uniqueness
  *of* the resolver's output; it does not define resolution.
- The **HTTP visibility leak** (friction #4 leak-half): separate
  `fix-http-visibility-leak`. This is the list-half complement.

## Implementation note — public-surface tier (2026-06-09)

`validate_composition` is exposed at **Tier 2** (its canonical home
`a2kit.runtime`, alongside `build`), NOT promoted to Tier 1 (`a2kit.*`).
ADR 0004 caps the `a2kit.*` front door at ≤10 **verb-authoring** names and
forbids adding `_LAZY_ATTRS` entries without a dedicated ADR; a composition
*validator* is not part of the 95% authoring surface, so it stays at the
longer public path. The spec's "expose from the public surface" is
satisfied by `from a2kit.runtime import validate_composition` (the same
module from which finishers already import `build`). If a future need
justifies front-door promotion, that is a separate ADR-0004 amendment.
