## Context

> **Corrected 2026-05-15 after reading-only spike.** The original
> draft of this design described the existing rule as "ctx in
> signature ⇒ ambient binds." That's not accurate. The actual
> rule is below.

**Existing behaviour (verified at `packages/mcp/server.py:55-99`
and `packages/cli/runtime.py:61-82`):**

Both transports unconditionally enter `ldd_state_for_call(...)`
for every framework-dispatched tool. The `ctx` placed into the
ambient is either:

- The real ctx (when the tool declares `ctx: ToolContext`; the
  transport injects it).
- `None` (when the tool does not declare `ctx`).
- A `StderrToolContext()` synthesized by the CLI runtime when
  `ctx_param_name` is set but kwargs don't contain it
  (`cli/runtime.py:65-66`).

LDD primitives (`event` / `report` / `log` / shorthands) read
ambient state and check `ctx`:

- `state is None` → `AmbientContextMissing` Mode A (`no_dispatch`)
  — only fires outside a framework dispatch.
- `state.ctx is None` → `AmbientContextMissing` Mode B
  (`missing_ctx_param`) — fires inside a dispatch when the tool
  didn't declare ctx.

So the actual existing rule is:

> Ambient state binds unconditionally on every dispatch.
> Ambient `ctx` is non-None iff the tool signature declares `ctx`
> (or the CLI runtime synthesized a `StderrToolContext`).

a2web's `del ctx` ceremony exists to make ambient `ctx` non-None
so LDD primitives don't raise Mode B. The tool body never reads
ctx; it's pure dispatcher-side hand-shake.

This is the real friction. The Router marker proposed below
addresses it precisely: opt the router into "synthesize ctx into
ambient for every tool, even when the tool body doesn't declare
it." LDD primitives stop raising Mode B; the tool body stays clean.

## The decision space

```
                  ┌─────────────────────────────────────┐
                  │ Where does the "this tool needs     │
                  │ ambient state" signal live?         │
                  └─────────────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────────┐
       │                      │                          │
   per-tool                router-level              app-level
 (today: ctx param,     (this change:             (App.ldd_default
  or rejected            emits_ldd)                — too coarse)
  @uses_ldd)
       │                      │                          │
       │                      │                          │
   ┌───┴───┐            ┌─────┴─────┐               ┌────┴────┐
   │ pros: │            │ pros:     │               │ pros:   │
   │ exact │            │ matches   │               │ zero    │
   │ scope │            │ how       │               │ per-    │
   │ cons: │            │ consumers │               │ tool    │
   │ cere- │            │ already   │               │ cere-   │
   │ mony  │            │ group LDD │               │ mony    │
   │ ×N    │            │ tools     │               │ cons:   │
   └───────┘            │ cons:     │               │ can't   │
                        │ slightly  │               │ mix     │
                        │ coarser   │               │ emitter │
                        │ than per- │               │ +non-   │
                        │ tool      │               │ emitter │
                        └───────────┘               │ routers │
                                                    └─────────┘
```

The router boundary is the natural grouping. Tools that share an
LDD emission pattern almost always share a router (they collaborate
in one capability). The exceptions — a router with mixed
emitter/non-emitter tools — are rare; when they happen, the tools
that need ctx declare it (the explicit per-tool path still works).

## Why not unconditional ctx synthesis

a2web's primary ask, restated against the corrected mental model:
synthesize a non-None ambient ctx for **every** framework-dispatched
tool, regardless of whether the tool declares `ctx`.

Two concrete failures:

1. **Spooky-action ergonomics (still the strongest argument).** A
   phase function four call-frames deep emits
   `a2kit.ldd.event(...)`. With unconditional synthesis, this
   works in any framework-dispatched call — there's no
   surface-level signal that the caller had to be a tool. With
   the current rule, the caller's signature carries `ctx` (or the
   router opts in via the marker proposed here), discoverable in
   one read. Per-tool unconditional synthesis erases the per-tool
   signal entirely; per-router opt-in preserves it at the right
   granularity (routers group tools by capability, so
   "this router emits LDD" is a meaningful read).

2. **Wire-side correctness.** For MCP transport, the wrapper
   needs to keep `ctx` in its rewritten signature so fastmcp
   injects it. Doing this unconditionally for every tool wastes
   the rewritten-signature slot when the consumer's tool truly
   has nothing to do with ambient state (a pure read-only health
   probe, a no-side-effect transform). The marker says "this
   router's tools want ambient ctx" — finer than per-app, coarser
   than per-tool, exactly right for the way consumers group
   LDD-emitting tools.

(Earlier draft of this design had a third argument about standalone
DI — withdrawn after re-reading the spike. Standalone DI never
enters the dispatcher path; this proposal doesn't affect it either
way. The relevant invariant is "dispatcher wraps in ambient state;
standalone caller wraps it themselves if they want it" — preserved.)

## Why not auto-detection

"If the tool's body calls `a2kit.ldd.*`, bind ambient." Sounds
clean. Not feasible:

- The call may be in a helper imported from another module,
  multiple frames down. Static AST inspection at decoration time
  doesn't see through indirection.
- Runtime inspection (first call observes a raise, recovers,
  retries with ambient) is a non-starter — the framework must
  not have observable-retry semantics for tool dispatch.

## Why not per-tool `@uses_ldd`

a2web's fallback ask. Equivalent cost to `ctx: ToolContext` (one
line per tool), and worse — it duplicates an existing concept
(LDD participation) via a new decorator. Violates "no multiple
ways to do the same thing."

## Why `emits_ldd: ClassVar[bool] = False`

- **Discoverable**: `class Foo(Router): emits_ldd = True` is a
  one-line opt-in, visible at the top of the router.
- **Default-safe**: `False` preserves today's behavior. Existing
  routers don't change.
- **Composable with explicit `ctx`**: a marker-on router that
  has one tool needing ctx in the body still declares `ctx`. The
  dispatcher injects ctx when declared, regardless of marker.
- **Class attribute, not instance attribute**: the marker is a
  static property of the router class, knowable at app build
  time. The dispatcher caches the wrap decision per tool at
  registration; no per-call branch needed.

## The dispatcher change (revised against actual code paths)

The change is **not** "introduce conditional ambient binding" —
binding is already unconditional. The change is **"control the
ambient `ctx` value when the tool body doesn't declare `ctx`."**

### MCP transport (`packages/mcp/server.py`)

Today: `_wrap_with_ldd_state` reads `ctx_param_name` from
`meta.context_param_name` (computed at decoration time in
`_verbs.py:126` via `find_context_param(fn)`). If set, the
wrapper pulls ctx from kwargs; if not, ambient ctx is None.

`_ensure_ctx_in_rewritten_signature` (`server.py:329-350`)
appends ctx to the rewritten signature when `ctx_param_name` is
set, so fastmcp injects it.

With the marker, we change two computed values to read from the
router as well:

```
effective_ctx_param_name = (
    meta.context_param_name
    if meta.context_param_name is not None
    else _synth_ctx_param_name()  # if owner_router.emits_ldd else None
)
```

Then:

- Rewritten signature includes `ctx` (so fastmcp injects).
- Wrapper pulls ctx from kwargs into `ldd_state_for_call`.
- Wrapper does NOT pass ctx to the tool body unless the original
  signature declared it.

### CLI transport (`packages/cli/runtime.py`)

Today: at lines 65-67, the runtime synthesizes
`StderrToolContext()` when `ctx_param_name` is set but missing
from kwargs. Same conditional adjustment: if the router marker is
set, behave as if `ctx_param_name` were set (for ambient purposes
only) — synthesize `StderrToolContext()` and feed it to
`ldd_state_for_call`, but do NOT inject into the tool body unless
the tool itself declared ctx.

### Registration-time caching

The marker is read on the **owner router class** at tool
registration time (per-tool computation; cached on
`A2KitMeta`). New field on metadata:

```
@dataclass(frozen=True)
class A2KitMeta:
    ...
    context_param_name: str | None = None
    ambient_ctx_via_router: bool = False  # NEW — set when owner has emits_ldd=True
```

Dispatcher hot path reads
`meta.context_param_name is not None or meta.ambient_ctx_via_router`
to decide whether to fish ctx out / synthesize it.

### Synthesized Parameter shape (MCP wrapper)

fastmcp's ctx injection is type-driven — `find_context_param`
(`signature.py:84-102`) matches by annotation via
`_is_tool_context(ann)`, not by parameter name. The existing
`_ensure_ctx_in_rewritten_signature` (`server.py:329-351`)
re-appends the *original* `inspect.Parameter` object from the
tool's signature.

For the marker case (tool has no ctx param; we synthesize one
into the rewritten signature so fastmcp injects), build a fresh
Parameter:

```python
import inspect
import fastmcp  # lazy import inside the helper (cold-start budget)

synth = inspect.Parameter(
    name="_a2kit_ctx",                  # single underscore; not dunder
    kind=inspect.Parameter.KEYWORD_ONLY,
    annotation=fastmcp.Context,         # MUST be the class, not a string
)
new_params.append(synth)
```

Two non-obvious constraints:

1. **Name**: use `_a2kit_ctx`, not `__a2kit_ctx__`. Dunder names
   trip Python's name-mangling rules in class scopes; the
   single-underscore convention is the standard "private-ish"
   marker and won't collide with consumer params.
2. **Annotation**: must be the actual `fastmcp.Context` class
   object. With `from __future__ import annotations` everywhere,
   string-form annotations exist on the original function. The
   synthesized Parameter must use the resolved class so fastmcp's
   introspection (which runs through `get_type_hints` internally)
   sees the right type.

The wrapper's body pops `kwargs["_a2kit_ctx"]` before dispatching
to the tool body, feeds it into `ldd_state_for_call`, and never
passes it to `fn(**kwargs)` (the tool body's signature doesn't
declare it). Per `_wrap_with_dispatch_hook` lines 277-281, the
existing pattern of popping the ctx kwarg before
`app._resolver.dispatch` already handles this — the marker case
just needs a parallel pop for the synthesized name.

## Backward compatibility

Zero impact on consumers who don't set `emits_ldd`. The default
preserves today's contract exactly.

For consumers like a2web who set the marker and drop `ctx` from
some tools:

- Their existing tools with `ctx` declared keep working — ambient
  still binds, ctx still injects.
- New tools without `ctx` get ambient binding (because of the
  marker) but no ctx kwarg.
- Old non-marker routers continue to require `ctx` for LDD —
  unchanged.

No loud-crash migration needed because no removal occurs. This
is purely additive.

## What we're NOT building

- A `@a2kit.uses_ldd` decorator on tools.
- An `App.ldd_default` setting.
- Auto-detection of LDD usage in tool bodies.
- Lint rule that fails CI for `del ctx` — the rule is advisory
  (suggests the marker), not a blocker.
- Documentation that `ctx` is "deprecated" — it isn't. Tools
  that need ctx in the body still declare it.

## Resolved questions

### Q1 — What exactly does the lint rule detect?

**Decision: "ctx declared, never referenced in body."**

The smell isn't `del ctx` specifically, and it isn't `_ctx` rename
specifically. It's the underlying state — *tool signature declares
`ctx`, tool body never reads it.* That state has three observable
forms, and detecting them individually is whack-a-mole:

1. `def fetch(*, ctx: ToolContext, ...): del ctx; ...` (a2web's
   current shape).
2. `def fetch(*, _ctx: ToolContext, ...): ...` (underscore convention
   for unused params).
3. `def fetch(*, ctx: ToolContext, ...): ...` (declared, never even
   `del`-ed, just unused).

Forms 2 and 3 don't even produce `del` statements; a `del`-only
rule misses them. Form 2 is *idiomatic Python* — we shouldn't flag
the rename pattern in general, only when the underlying state is
"ctx declared on a marker-eligible router with no body reference."

Rule logic:

```
for tool in router.tools:
    if router.emits_ldd:
        # Marker already opts in; no smell. Skip.
        continue
    ctx_param = find_ctx_param(tool.signature)  # ctx OR _ctx
    if not ctx_param:
        continue
    if name_referenced_in_body(tool, ctx_param.name):
        continue
    emit_advisory(
        tool,
        f"`{ctx_param.name}` declared but unused. Consider setting "
        f"`emits_ldd = True` on {router.__name__} and dropping the "
        f"param. See add-router-ldd-marker."
    )
```

AST inspection at lint time, not runtime. The "name referenced in
body" check uses a `Name` visitor on the function body — same
technique as the existing `purity` / `caps` rules. Indirect
references (e.g. `locals()["ctx"]`) are out of scope; the lint is
best-effort.

Rule lives under `packages/lint/rules/ldd.py` (existing LDD-rule
home) as advisory severity. Consumers can `--strict-advisory` if
they want it to fail build.

### Q2 — Should standalone DI resolution gain its own ambient CM?

**Decision: out of scope. Not adding now.**

Standalone DI (`Container.resolve(T)` outside a tool dispatch) is
an advanced surface — added in v0.36, used by no consumer who has
reported friction. The motivation in a2web's feedback is
*dispatched-tool* ergonomics; standalone callers already invoke
resolution explicitly and can wrap in `ldd_state_for_call(...)`
themselves if they need LDD emissions during the resolution.

Three reasons to defer:

1. **No consumer signal.** a2web's friction is router-tools, not
   standalone. Building ambient support for a surface with zero
   complaints is speculative API.
2. **Uniform rule preservation.** Today: dispatched tool with `ctx`
   → ambient; standalone resolve → no ambient. After this change:
   dispatched tool with `ctx` OR on marker router → ambient;
   standalone → still no ambient. The rule stays "framework
   dispatches = framework binds ambient; consumer dispatches = consumer
   binds ambient." Adding a third path muddies the model.
3. **Cheaper to add later than to remove.** If a consumer reports
   the gap, we add it then with concrete evidence.

If standalone callers want LDD during resolution today, they wrap:

```python
async with a2kit.ldd.ldd_state_for_call(ctx=stub, ...):
    obj = await container.resolve(T)
```

That's the current escape hatch. It stays. No follow-up filed.
