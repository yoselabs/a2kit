## Context

a2kit v0.32 surface was audited against three vectors:
1. **MCP spec semantics** — which decorator kwargs are meaningful per verb.
2. **Real consumer usage** — a2web (live), a2atlassian/a2db (migrating in days), examples/, tests/.
3. **README claims vs runtime** — `hasattr` checks against documented symbols.

The audit found one production bug, five accept-invalid footguns, several zero-usage kwargs and one zero-usage verb, two redundant decorator pathways, and ~10 stale README references. Fixing this in one v0.33 pass is cheaper than incremental cleanup; consumers about to migrate get a sharper surface from day one.

This is a **breaking-release pass**, not a deprecation cycle. Per `CHANGELOG.md` precedent (v0.30–v0.32 were three breaking releases in 30 hours, all migrated cleanly in single sessions), a2kit's "loud failure with embedded migration hint" pattern absorbs small breaking surfaces well. Every removed/restricted API raises a `TypeError`/`ValueError` whose message names the dropped symbol and the replacement.

## Goals / Non-Goals

**Goals:**
- No silent acceptance of invalid kwargs anywhere on the verb decorators or `App` composition surface.
- `<app> health` works on fresh installs without dev extras.
- README and live code agree on every public symbol; CI enforces it.
- Consumer pain on v0.32 → v0.33 migration stays in the same range as the v0.30/v0.31/v0.32 migrations a2web absorbed (≤ 1 session, ≤ 250 LOC).

**Non-Goals:**
- App-as-root-router (`@app.read` directly on App) — deferred to a follow-up change after a2atlassian migration produces friction signals.
- `app.singleton(T, factory, teardown=fn)` (W1) — deferred to its own change; large enough to design separately, depends only on container internals.
- Router-tools orphan detection (W2) — separate change; lint + runtime, independent of this prettification pass.
- `provide` → `add_provider` and `singleton` → `add_singleton` rename — deferred; rename pass deserves its own coordinated change with alias retention.
- `--select` mechanism on routers — deferred to v0.34 once a2atlassian indicates real demand.
- `set_ldd` rework / dispatch-hook public setter — deferred.
- Surface enum (Flag-based `Surface.CLI | Surface.MCP`) — out; the code shape `Visibility = Literal[...]` is what ships, README will be corrected to match.

## Decisions

### D1. Decouple `<app> health` from `a2kit.packages.testing` (not just guard the pytest import)

The reported bug is fixable two ways:
- **Option A** — guard `import pytest` in `fixtures.py` with `TYPE_CHECKING` (1-line fix).
- **Option C** — refactor `health_cmd` so it builds the probe call from `app.container()` + `app._health` directly, with no test-client import at all.

**Choice: Option C.**

Rationale: the test client is a heavyweight dependency to drag into a production CLI subcommand. Option A fixes today's symptom; Option C kills the entire dependency edge. The probe data the test client returned (`status` + per-check results) is already produced by `a2kit.packages.health.run_checks(app)` — the helper the test client itself invokes. `health_cmd` can call it directly with `asyncio.run` and the App's `lifespan_cm`.

Cost: ~20 LOC in `builder.py` plus a smoke test that imports a fresh venv with no dev deps and runs `<app> health`.

### D2. `@app.health_check` auto-enables the health tool

Today, `App(health_tool=True)` installs the `_meta.health` synthetic router, but `@app.health_check` decorator registers checks into a registry whether or not the tool is installed. Mismatch is silent dead code.

**Choice:** first call to `@app.health_check` auto-installs the `_meta.health` router (idempotent — subsequent calls are no-ops). `App(health_tool=True)` becomes a no-op when checks are registered (still accepted for explicit-eager use cases, e.g., apps that want the tool present even with zero checks). Eventually the flag becomes redundant; deprecation noted in a later change.

Alternative considered: raise `ValueError` if `@app.health_check` is called without `health_tool=True`. Rejected — flag-and-decorator combos are an antipattern; auto-enable is the lighter consumer experience.

### D3. `idempotent=` on `@read`/`@list_` raises (mirrors existing `destructive=` rejection)

The existing precedent: `@a2kit.read(destructive=True)` raises `TypeError` because the spec says `destructiveHint` is meaningful only when `readOnlyHint=false`. `idempotentHint` has the same spec condition (also "meaningful only when readOnlyHint=false") but isn't enforced. This change adds the symmetric guard.

The MCP spec is about *environment effect*, not return-value stability — a read returning time-varying data (`get_current_time`) is still spec-idempotent because calling twice has no environment effect. We don't conflate the two. The TypeError message says exactly this: "read tools are idempotent by spec; pass to `@a2kit.write` if you mean a write that is repeat-safe."

### D4. `@a2kit.list_` rejects non-list returns at decoration

Currently `_derive_selectable_fields` walks the return annotation, expects `list|tuple|set|frozenset` origin, and silently returns `()` for anything else. The tool decorates successfully but selectable fields are empty — confusing list-view shape with no error trail.

**Choice:** raise `TypeError` at decoration if `typing.get_origin(return_annotation)` is not in `{list, tuple, set, frozenset}`. The check moves into `list_()` decorator body before `_derive_selectable_fields`. Message includes the actual return annotation and the expected `list[T]` shape.

### D5. Drop `@a2kit.tool` bare verb

Zero consumer usage across a2web, a2atlassian, a2db, examples/. Internal a2kit tests use it only to test the lint rules that operate on it — those tests can switch to `@a2kit.write(destructive=False, ...)` to test the same lint paths.

Migration message in the removed-import path: `@a2kit.tool` was removed in v0.33; use `@a2kit.read` for read-shaped, `@a2kit.write` for write-shaped, or `@a2kit.list_` for list-shaped tools.

### D6. Drop `name=` kwarg on public verb decorators; preserve internal alias

Three usage sites total: one internal (`app.py:151` for `_meta.health`), two test fixtures (`test_health.py:123`, `test_listview_e2e.py:31`).

**Choice:** drop `name=` from public verb signatures (`tool`, `read`, `write`, `list_`). The internal `_meta.health` registration continues to work via a private `_read_internal` helper that exposes `name=`. Test fixtures move to either using natural method names (preferred) or invoking the private helper directly (when they specifically test name-override semantics).

This shrinks the public verb signature to: `(*, idempotent?, open_world?, destructive?, title?, visibility?, reports?)` for `@write`; `(*, open_world?, title?, visibility?, reports?)` for `@read` / `@list_`.

### D7. Drop `app.singleton(T)` decorator form; keep method-call form only

`app.singleton(T)` returning a decorator is unused outside one test fixture. Removing it:
- frees the signature for `app.singleton(T, factory, teardown=fn)` in the follow-up W1 change without overloading `None`-as-decorator vs `None`-as-class-as-factory semantics.
- matches `app.provide` which already has no decorator form (validated by audit).

Method-call form `app.singleton(T, factory)` is the only path. Where `factory` is a class with a DI-introspectable `__init__`, `app.singleton(T)` (no second arg) still works as class-as-factory, same as `app.provide(T)`.

### D8. `app.tools()` returns `list[ToolDescriptor]`; drop `app.tool_descriptors()`

Today: `app.tools()` returns raw callables, `app.tool_descriptors()` returns `ToolDescriptor` objects, `fn._a2kit` exposes the frozen meta. Three accessors, three return shapes.

**Choice:** `app.tools()` returns `list[ToolDescriptor]`. Drop `app.tool_descriptors()`. `fn._a2kit` stays as the runtime attribute (decorator stamps and reads it internally) but is not promoted in public docs.

`ToolDescriptor` already carries everything the old `app.tools()` return needed: `.fn` for the callable, `.meta` for verb/tags/annotations, `.slug` for the router, `.name` for the wire name. Consumers that want callables: `[d.fn for d in app.tools()]`.

### D9. Drop stacked `@reports(T)`; keep `reports=T` kwarg on verb decorators

Two paths to declare the report type today. The kwarg form lives on the verb decorator (next to `idempotent`, `open_world`, etc.) — same "annotations stamped on the verb" mental model. The stacked decorator is a leftover from v0.21.

**Choice:** drop `@reports(T)` from `a2kit.packages.mcp.reports`. `reports=T` kwarg on `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` is the only path. The lint rule `A2K-LDD-REPORT-TYPE`'s "type defined inside a function" branch becomes unreachable (the kwarg form requires the type to be importable into the decoration site) — simplify the rule.

### D10. `AmbientContextMissing` message distinguishes two modes

Implementation in `_require_ambient_state`:
- contextvar unset → "called outside an active tool dispatch" (existing wording, unchanged)
- contextvar set but `state.ctx is None` → "called from a tool body that did not declare `ctx: a2kit.ToolContext` as a parameter; add the parameter to the tool signature, or remove the LDD call"

Two raises, same exception class, different messages. No API change.

### D11. README drift CI test

A new test (`tests/test_readme_symbol_drift.py`) parses `README.md`, extracts every claimed `a2kit.X` / `App.X` / `Router.X` / `@a2kit.X` reference, and asserts each resolves on the live module/class. Fails the lint target.

Parser strategy: regex over fenced code blocks and inline `` `...` `` spans matching the symbol patterns. False positives (e.g., `app.tools()` inside prose) are acceptable because they would also be correct symbol references. False negatives (symbol claimed in prose without backticks) are tolerated for v0.33 — tighten in a follow-up if drift recurs.

Initial run will fail on the ~10 `@app.on_startup` / `@app.on_shutdown` references and the `Surface` enum claim. README fix lands in the same PR.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Breaking changes pile up on a single release | All five footguns + four dead-surface removals follow a2kit's "loud failure + migration hint" convention. The v0.30 → v0.32 cascade (three breakings in 30 hours) was absorbed cleanly per a2web feedback. |
| README drift CI test produces flaky failures on prose mentions of symbol names | Match only within backtick spans and fenced blocks. Tolerate ambiguity (false positives are still valid claims). |
| Auto-enable on `@app.health_check` could surprise users who registered checks but didn't want the tool installed | The `_meta.health` tool is hidden from agent-facing `list_tools`. It only becomes invokable via name. If a consumer wants registered-but-uninstalled, document the workaround (don't register the check). |
| Decoupling `health_cmd` from testing means we maintain a thin duplicate of the test-client's invocation path | Refactor `run_checks` (already in `a2kit.packages.health`) as the shared core; `health_cmd` calls it directly, the test client also routes through it. No duplication. |
| Tests asserting "current accept-invalid behavior" need to flip | Audit identified exact tests: `test_verb_annotations.py:36, 105-119`, `test_health.py:39-42, 123`, `test_listview_e2e.py:31`. Each flips to assert the new raise or moves to internal-alias usage. |
| Consumers pinning v0.32 won't see the new constraints until they upgrade | Acceptable. a2web pins to v0.32 today; the migration to v0.33 will be the next session. a2atlassian/a2db pin to v0.33 from the start. |

## Migration Plan

Single coordinated release `a2kit v0.33.0`.

Step-by-step for consumers (covered in `CHANGELOG.md` for v0.33):

1. **`@a2kit.tool` → `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`.** Pick the verb that matches the tool's semantics. The bare-tool case usually wants `@write(destructive=False)`.
2. **`name=` kwarg → rename the method.** Auto-derivation from `fn.__name__` handles most cases (`list_tasks` → `list-tasks`).
3. **`@app.singleton(T)` decorator form → `app.singleton(T, factory)` method form.** Define the factory as a top-level function or lambda, pass it explicitly.
4. **`app.tool_descriptors()` → `app.tools()`.** Return type changed from `list[Callable]` to `list[ToolDescriptor]`; if you only wanted callables, map `[d.fn for d in app.tools()]`.
5. **`@reports(T)` stacked → `reports=T` kwarg on verb.** Drop the import, move to kwarg.
6. **`@a2kit.read(idempotent=True)` → drop the kwarg.** Reads are idempotent by spec.
7. **`@a2kit.list_` non-list return → fix the return annotation.** Use `list[T]`.
8. **`@a2kit.list_(page_size=0)` → use a positive integer or omit.**
9. **`@a2kit.tool(annotations=..., idempotent=...)` → pick one path.** Flag kwargs OR explicit annotations object, not both.
10. **`App(health_tool=True)` is now a no-op** when `@app.health_check` is also used; can be removed safely.

No silent breakage paths. Every removal raises at decoration / construction time with a message pointing at the replacement.

## Open Questions

None blocking. The deferred items (App-as-Router, `add_provider` rename, `--select`, set_ldd rework, teardown=, orphan detection) each become their own change once this prettification lands and a2atlassian's migration produces friction signals.
