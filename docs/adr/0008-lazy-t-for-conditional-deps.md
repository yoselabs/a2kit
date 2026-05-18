---
id: "0008"
status: accepted
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [di, surface, authoring]
deciders: [Denis Tomilin]
---

# ADR 0008: `Lazy[T]` for conditional dependencies, not `await app.resolve(T)`

## Status

Accepted, 2026-05-18. Backfilled — the decision was settled when
`Lazy[T]` shipped (v0.18 era) and was reinforced in v0.36 (lazy-CM-
aware container) and v0.39 (`Lazy[T]` recognition in factory params).
This ADR records the rationale that previously lived only in
`docs/patterns/conditional-deps.md`.

## Summary

In the context of tools that *might* need an expensive resource on
a given dispatch but not always (a2web's `extract` is the canonical
case: sometimes JS rendering, sometimes plain HTTP, sometimes LLM-
assisted), facing the question of how authors should opt into
on-demand resolution, we decided to recognize `Lazy[T]` in tool
signatures (the dispatcher passes a zero-arg async closure that
enters the resource on first await) and against requiring authors
to write `await app.resolve(T)` inside the tool body, to achieve
declarative conditional dependency declaration that the dispatcher
can introspect, schedule, and clean up scope-correctly, accepting
that the closure shape (`Callable[[], Awaitable[T]]`) is a learned
idiom and that `Lazy[T]` cannot deliver instances synchronously.

## The problem

A tool that always needs a resource declares it directly:

```python
async def extract(url: str, browser: Browser) -> str:
    return await browser.scrape(url)
```

The dispatcher resolves `Browser`, calls `__aenter__` on it, threads
it through, calls `__aexit__` on exit. Simple, but eager: every
`extract` dispatch instantiates a `Browser` even if `url` is a
static HTML page that does not need JS rendering.

The motivating real case is a2web's `extract` tool: a single
function whose work depends on the URL — sometimes plain fetch,
sometimes JS-rendered, sometimes LLM-assisted. Eager declaration
of all three dependencies makes every dispatch pay for every
resource. Authors have a "five-resource tool only uses one"
problem and need a way to declare *availability* without forcing
*instantiation*.

The natural Python answers are:

1. **Service locator inside the tool body** — `browser = await ctx.get(Browser)`.
2. **Optional positional resolution** — `await app.resolve(Browser)`
   inside the body.
3. **A type wrapper at signature level** — `browser: Lazy[Browser]`,
   the dispatcher passes a closure.

The dispatcher is the place that knows resource lifecycles. The
question is whether the conditional-dependency *expression* should
also live in the dispatcher's view (option 3) or escape into the
body (options 1 and 2).

## What we considered (and why this one)

### Option 1: Service locator — `ctx.get(T)` inside the body

```python
async def extract(url: str, ctx: a2kit.ToolContext) -> str:
    if needs_js(url):
        browser = await ctx.get(Browser)
        return await browser.scrape(url)
    return await plain_http_get(url)
```

Why it lost:

- **Hidden dependency.** The tool's contract is its signature.
  `ctx.get(Browser)` hides `Browser` from the signature; readers
  must scan the body to know what the tool depends on. Same critique
  as classic service-locator anti-pattern.
- **Dispatcher cannot introspect.** The dispatcher does not know
  which resources `extract` *might* touch. It cannot pre-warm,
  pre-flight, or build a dependency graph. Every `ctx.get` is a
  runtime surprise.
- **Cleanup model unclear.** Does `ctx.get` enter the resource? Who
  exits it? When? The body has to know the lifecycle, which is
  exactly what the dispatcher exists to abstract.

### Option 2: Resolve at use site — `await app.resolve(T)`

```python
async def extract(url: str) -> str:
    if needs_js(url):
        browser = await app.resolve(Browser)
        return await browser.scrape(url)
    return await plain_http_get(url)
```

A variation on option 1 — same problem set, slightly different
shape. The tool body imports `app` (or receives it via DI), calls a
resolve method directly. Same anti-patterns: hidden dependency,
opaque to the dispatcher, ambiguous cleanup.

Why it lost: same reasons as option 1, plus `app` is then either
a global (bad) or a parameter (you've just reinvented the
service-locator pattern with extra steps).

### Option 3: `Lazy[T]` in the signature (chosen)

```python
async def extract(url: str, browser: Lazy[Browser]) -> str:
    if needs_js(url):
        b = await browser()
        return await b.scrape(url)
    return await plain_http_get(url)
```

`Lazy[T]` is `Callable[[], Awaitable[T]]`. The dispatcher recognizes
the type and passes a zero-arg async closure that, on first await,
runs the resource's `__aenter__` and caches the result for the rest
of the call (per the resource's scope). If never awaited, `__aenter__`
is never called. The closure honours the resource's scope — app-scope
`Lazy[T]` returns the same instance across calls; per-call `Lazy[T]`
returns a fresh instance per dispatch.

Why it wins:

- **Dependency is in the signature.** A reader sees `Lazy[Browser]`
  and knows the tool can use a `Browser` — and that it might not.
  The contract is visible without reading the body.
- **Dispatcher introspects normally.** `inspect.signature(extract)`
  shows `Lazy[Browser]`; the dispatcher pre-builds the dependency
  graph, knows what resources to make available, and can fail fast
  if a `Lazy[T]` parameter has no provider registered.
- **Cleanup is scope-correct without author work.** Awaiting `browser()`
  enters via the lifecycle the resource registered with (app-scope or
  per-call). The dispatcher's exit stack closes it at the right time.
  Never-awaited closures incur zero entry and zero exit.
- **Composable with other DI features.** A factory function can take
  `Lazy[T]` parameters too (v0.39 recognition extension); the dispatcher
  recurses through the same mechanism. Service-locator patterns would
  require parallel composition logic.

### Option 4: Hybrid — both `Lazy[T]` and `ctx.get(T)`

Ship both. Authors pick.

Why it lost: violates CLAUDE.md core principle 2 ("no multiple ways
of doing the same thing"). Two ways to express the same intent
means two ways to teach, lint, and maintain. `Lazy[T]` dominates
on every axis except brevity-of-keystroke, and the brevity argument
is marginal.

## The decision

a2kit's dispatcher recognizes `Lazy[T]` (alias for
`Callable[[], Awaitable[T]]`) in both tool parameters and factory
parameters. The dispatcher passes a closure that:

1. On first `await`, runs the resource's `__aenter__` and caches the
   result for the remainder of the call (or the app's lifetime, for
   app-scope resources).
2. On subsequent `await`s within the same scope, returns the cached
   instance without re-entering.
3. If never awaited, the resource is never entered — zero cost.

`a2kit.packages.di.Lazy` is the canonical type alias (see ADR 0004
for why it stays in `a2kit.packages.*` rather than promoting to
top-level). The dispatcher recognizes both the alias and the raw
`Callable[[], Awaitable[T]]` shape — type-checking aliases through
other names also works.

There is **no** `ctx.get(T)` or `app.resolve(T)` body-side service
locator. Authors who try to write one will find no such method on
`ToolContext` or `App`; the error guides them to `Lazy[T]`.

## Consequences

### Positive

- Tool contracts are visible at the signature. Readers (human or
  AI) understand the dependency set without reading the body.
- The dispatcher owns lifecycle. Authors do not write `__aenter__` /
  `__aexit__` calls; they `await closure()` and the dispatcher
  handles entry, caching, and exit.
- Zero-cost when unused. A tool with three `Lazy[T]` params that
  uses one on this dispatch pays for one resource entry.
- Composes with factory injection. `Lazy[T]` in factory params (v0.39)
  means service classes can declare conditional sub-dependencies
  without writing service-locator code.
- The "five-resource tool only uses one" problem is solved
  declaratively, not procedurally.

### Negative

- The closure idiom (`b = await browser()`) is a learned step. New
  authors expect the dispatcher to hand them a `Browser` directly
  and have to read either the conditional-deps pattern doc or this
  ADR to understand the indirection.
- No synchronous resolution. `Lazy[T]` is async-by-construction;
  tools that need a resource in a synchronous context must declare
  it as `T` directly (which is eager).
- `Lazy[T]` does not (currently) support per-resource lazy-import
  control beyond the resource's own `__aenter__` implementation. If
  a resource is expensive to *import* (not just to enter), authors
  need a separate pattern (lazy submodule imports inside the
  factory). Out of scope for this ADR.
- Service-locator-curious contributors will look for `ctx.get(T)`
  and not find it. This ADR is the answer; until they find it,
  there is one minute of friction.

## References

- `docs/patterns/conditional-deps.md` — usage tutorial (how-to layer).
- `src/a2kit/packages/di/` — `Lazy[T]` type alias and dispatcher
  recognition. See also the v0.36 lazy-CM-aware container.
- ADR 0004 — why `Lazy` stays in `a2kit.packages.di.*` instead of
  being promoted to top-level `a2kit.Lazy`.
- CHANGELOG.md v0.39.0 — `Lazy[T]` recognition extended to factory
  parameters, closing the consumer-facing spec drift.
