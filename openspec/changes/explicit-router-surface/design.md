# Design — Explicit Router surface

## Context

FastMCP's "magic ceiling" maxim — *the framework reads what you wrote,
never invents what is missing* — is the design constraint that makes
its tools auditable by `grep`. a2kit's `Router` base breaks this in
three places (A1 slug derivation, A2 `dir()` walk, A3 staged-extras
side channel). The fix is uniformly the same: replace inference with
an explicit attribute the author writes once.

This design records the option space considered, the rationale for
the chosen shape, and the migration plan.

## Decisions

### D1. Slug is a `ClassVar[str]` class attribute. No constructor arg.

Considered:

- (a) `class TasksRouter(Router, slug="tasks"):` —
  `__init_subclass__` keyword arg.
- (b) `class TasksRouter(Router): slug = "tasks"` — plain class
  attribute, `Router.__init__` asserts it's set.
- (c) `TasksRouter(slug="tasks")` — constructor arg only.

Chosen: **(b)**. It is the only option where:

- A type checker (ty, mypy) sees the attribute on the class.
- A reader scanning the subclass body sees the slug immediately,
  with no decorator or subclass-arg syntax to decode.
- No `__init_subclass__` magic runs (which is exactly the kind of
  ceiling-breaking inference we are trying to eliminate).
- A `grep "slug = "` on the repo enumerates every Router slug in
  one shot.

(a) is rejected because `__init_subclass__` recreates the same "read
the framework to know what happened" problem with different syntax.
(c) is rejected because slug is a class identity, not a runtime
parameter; putting it in `__init__` invites different instances of
the same class registering with different slugs, which is a
worse-than-current footgun.

`Router.__init__` enforces presence with a clear error:

```
TypeError: Router subclass TasksRouter must define class attribute
'slug: ClassVar[str]'. Example: `slug = "tasks"`.
```

### D2. Tools are a `ClassVar[tuple[Callable, ...]]`. No introspection.

Considered:

- (a) `tools = (fetch, update)` — explicit tuple of method
  references.
- (b) `__init_subclass__` snapshots `vars(cls)` at class-creation
  time, stashes the tool list on `cls._a2kit_tools`.
- (c) Keep `dir()` walk, just suppress the bare-except branch
  (per `loud-degrade-everywhere`'s original intent).

Chosen: **(a)**. Same reasoning as D1: it's the only option that
puts the answer on the page. (b) is a smaller-magic version of the
current behaviour but still answers "which methods?" via
introspection — even if at class-creation time. (c) leaves the
ceiling violation in place.

Implementation note: the tuple stores **unbound method references**
(e.g. `(fetch, update)` where each is the function defined inside
the class body). `Router.__init__` resolves each entry to the bound
method via `getattr(self, fn.__name__)`. This is the same shape
fastmcp's `@server.tool` registration uses internally.

A linter rule (tracked as a follow-up TODO in tasks.md) detects
methods decorated with `@a2kit.read/write/list_/tool` that aren't
listed in `tools`, and vice versa. The rule is not blocking for
this change — runtime check in `Router.__init__` already raises if
a listed method has no `_a2kit` meta.

### D3. Staging decorators fold into verb-decorator kwargs.

Considered:

- (a) Add `reports=`, `enrichers=`, etc. as kwargs on each verb
  decorator; remove staging entirely.
- (b) Keep staging but document the side-channel attribute.
- (c) Replace staging with a class-level mapping
  (`reports = {"fetch": Task}`) on the Router.

Chosen: **(a)**. The stacked decorator was a workaround for not
wanting to grow verb-decorator signatures. The cost was readers
having to trace two decorators to understand one tool. Folding into
kwargs makes the verb decorator the single source of truth for
per-tool configuration; readers see everything in one place.

(b) preserves the ceiling violation. (c) creates a new
indirection — readers now scan the Router for a `reports` mapping
instead of reading the decorator. (a) is the only option that
respects "one tool, one decorator block, one source of truth."

The full kwarg surface for verb decorators after this change:

```python
@a2kit.read(
    *,
    name: str | None = None,
    tags: frozenset[str] = frozenset(),
    annotations: ToolAnnotations | None = None,
    idempotent: bool = False,
    open_world: bool = False,
    title: str | None = None,
    reports: type | None = None,
    enrichers: tuple[Callable[[Exception], str | None], ...] = (),
)
```

`@a2kit.write` and `@a2kit.tool` add `destructive: bool = True`.
`@a2kit.list_` adds the list-view positionals plus `page_size`,
`selectable_fields`.

(Note: `enrichers=` on the verb decorator is per-tool override.
Router-level `enrichers: ClassVar[...]` from `router-conventions`
remains the default. Per-tool kwarg wins when both are present.)

### D3.5. Remove the `Router.install(self, app)` side-channel hook.

`src/a2kit/app.py` currently reads `getattr(router, "install", None)`
and, if present, calls it. That hook is redundant with the explicit
`providers` tuple and `lifespan` method this proposal already
requires: any provider registration or wiring done in `install` can
(and SHALL) live in `providers` / `lifespan` instead. Two surfaces
doing the same job is exactly the redundancy this proposal exists to
remove.

The discovery surface is **closed**: `slug`, `tools`, `providers`,
`lifespan`. Nothing else. The `getattr(router, "install", ...)`
call site is deleted; any test exercising it is removed.

### D4. Version bump: v0.31.0 (paired with `lifespan-over-lifecycle-hooks`).

**Decision: v0.31.0.** Both proposals ship together; neither lands
alone.

Rationale for not going v1.0 yet:

- The Router providers/`on_startup`/`on_shutdown` side-channel was
  the v1.0-blocker for the Router surface. This revision closes it
  (A2.5 + A2.6 explicit `lifespan` + explicit `providers`).
- However, two larger above-ceiling items remain pending and
  block a credible v1.0:
  - **A4 — signature rewrite** (tool method signatures normalised
    to a single canonical shape). Not in this proposal.
  - **A6 — wire-scope synthesis** (wire envelope assembled from
    typed sources, not stitched from string keys). Not in this
    proposal.
- Bundling A4/A6 into v1.0 would push the date by months and break
  more author code at once than is healthy. Shipping v0.31.0 with
  Router + lifecycle paired keeps the breaking-change blast radius
  small and lets v1.0 come when A4/A6 have proposals of their own.

Sequencing within v0.31.0:

1. `lifespan-over-lifecycle-hooks` lands first (introduces
   `a2kit.lifespan.compose(*lifespans)` and removes
   `@app.on_startup` / `@app.on_shutdown`).
2. This proposal lands second (consumes `compose(...)` in
   `App.add_router` to fold `Router.lifespan` into the App's
   top-level lifespan; introduces the rest of the explicit Router
   surface).

CHANGELOG names both changes in a single v0.31.0 entry with the
combined migration matrix (slug + tools + providers + lifespan +
reports + app-lifespan).

## Risks

- **R1. Boilerplate fatigue.** Every Router gains two class
  attributes. Mitigation: it really is two lines, and they replace
  a class-name suffix convention plus implicit discovery — neither
  of which the type checker could see. Net DX is positive once a
  reader has to debug a Router with shadowed slugs or missed
  tools.

- **R2. Tools tuple drift.** Author decorates a new method but
  forgets to add it to `tools`. Mitigation: runtime stamp loop in
  `Router.__init__` doesn't see the new method, so it never
  registers — surfaces immediately the first time the author tries
  to call the tool. The follow-up lint rule turns this from
  "first-call surprise" into "static error."

- **R3. Migration sweep miss.** A `@reports` call site in
  `examples/` gets missed, breaks at runtime. Mitigation: the
  removal of `stage_extra` makes any surviving `@reports` import
  fail at import time, not silently at runtime. The sweep is
  mechanical (`rg "@reports\(" -t py`).

- **R4. Cross-proposal ordering.** If
  `align-with-pydantic-and-stdlib` lands first, its typed
  `A2KitMetaExtras` shape is populated by both this proposal's
  verb-kwarg path AND the legacy staging path until this proposal
  lands. That's fine — both write to the same destination shape.
  No ordering constraint.

## Migration plan

### Migration footprint

`grep -rE "class \w+\((?:a2kit\.)?Router.*\):" src/ tests/ examples/`
across this repo finds **86 Router subclass declarations** (most
are in `tests/`, plus a handful in `src/a2kit/packages/...` and the
five `examples/*` apps). Roughly 5–10 distinct subclass *files*
need slug + tools + (where applicable) lifespan/providers stamps;
the rest are test-local one-shot classes that get the same
treatment in bulk.

### Migration

Users hand-rewrite call sites; every rewrite is mechanical. No
codemod, no shim, no deprecation cycle.

### Steps

1. **Slug sweep (A1).** `rg "class \w+Router\(.*Router.*\):" -t py
   --vimgrep` lists every Router subclass. For each, add `slug =
   "<derived>"` matching today's derived value. One commit per
   logical surface (src/, examples/tracker/, examples/web/, …).
   No behaviour change at this point — the framework still
   derives, but every subclass also writes the answer down.

2. **Tools sweep (A2).** Same enumeration. For each Router, list
   every method decorated with `@a2kit.read/write/list_/tool` into
   a `tools = (m1, m2, ...)` class attribute. No behaviour change
   yet.

3. **Reports sweep (A3).** `rg "@reports\(" -t py --vimgrep`. For
   each call site, move the type argument into the adjacent verb
   decorator as `reports=T` kwarg.

4. **Framework cutover.** Land the four removals together:
   `_derive_slug`, `_collect_methods` (`dir()` walk), `stage_extra`
   + `PENDING_EXTRA_ATTR`, and the `@reports` definition. Add the
   required-attribute assertions in `Router.__init__` and the
   `reports=` kwarg on verb decorators. Tests in
   `tests/test_routers.py` and `tests/test_metadata.py` get
   rewritten to assert the new contracts.

5. **Release.** Bump version per D4. CHANGELOG names every surface
   the author needs to touch with a one-line migration example
   per surface.

## Out of scope

- The linter rule that detects `@a2kit.read`-decorated methods
  missing from `tools`. Tracked as a TODO in `tasks.md`; not
  blocking for v1.0.
- Whether `enrichers` per-tool kwarg should also accept a single
  callable (not just a tuple). Defer to a follow-up if authors
  ask.
