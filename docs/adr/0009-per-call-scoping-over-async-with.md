---
id: "0009"
status: accepted
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [di, surface, authoring, lifecycle]
deciders: [Denis Tomilin]
---

# ADR 0009: `per_call=True` resource scoping over explicit `async with` in tool body

## Status

Accepted, 2026-05-18. Backfilled — the decision was settled with the
DI container's scope model (v0.36 era). This ADR records the
rationale that previously lived only in `docs/patterns/transactions.md`.

## Summary

In the context of resources whose lifecycle is one tool dispatch
(the canonical case is a database transaction: acquire, BEGIN, run,
COMMIT/ROLLBACK, release), facing the question of who owns the
`__aenter__` / `__aexit__` calls, we decided to ship a `per_call=True`
flag on `app.provide(T, factory, per_call=True)` that makes the
dispatcher enter and exit the resource around each tool call (with
exception forwarded to `__aexit__`), and against asking authors to
write `async with Transaction(...) as tx:` inside the tool body, to
achieve uniform lifecycle handling between app-scope and per-call
resources (both come in via DI, both clean up via the dispatcher's
exit stack) and to keep tool bodies focused on business logic,
accepting one declaration-site mode flag and one scope-direction
rule (per-call may depend on app-scope, never the reverse).

## The problem

Some resources outlive a tool call (a connection pool, an HTTP
client, an LLM provider). Some last exactly one call (a database
transaction, a per-request cache, a tracing span). The DI container
already knows how to construct, cache, and clean up app-scope
resources — `__aenter__` on entry to `async with app:`, `__aexit__`
on exit.

The question is how per-call resources fit. Three shapes:

1. **Explicit `async with` in the body** — author writes the
   transaction lifecycle manually.
2. **Per-call DI flag** — `app.provide(Transaction, per_call=True)`,
   the dispatcher enters/exits around each call.
3. **No framework support** — author manages everything (acquire,
   begin, commit/rollback, release) by hand without `async with`.

A transaction is the worst case: forgetting `__aexit__` means a
leaked connection AND an uncommitted/un-rolled-back transaction.
The framework choice has to make the correct path the easy path.

## What we considered (and why this one)

### Option 1: `async with` in the tool body

```python
async def transfer(pool: ConnectionPool, src: str, dst: str, amount: int) -> None:
    async with Transaction(pool) as tx:
        await tx._conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, src)
        await tx._conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, dst)
```

Why it lost:

- **Two lifecycle models in one body.** App-scope resources arrive
  via DI parameters with implicit dispatcher-managed lifecycle.
  Per-call resources require explicit `async with`. Authors learn
  two patterns for one concept; reviewers check for two leak
  classes.
- **Construction in the body couples to construction details.**
  `Transaction(pool)` in the body means the body owns the
  transaction's construction signature. Changing `Transaction`'s
  constructor (add a logger, change pool acquisition semantics)
  forces edits across every tool. With DI, the factory absorbs
  the change.
- **The most common shape (transaction) becomes verbose.** Every
  tool that touches the DB has an `async with` block. Boilerplate.
- **Authors who forget `async with` have a footgun.** A bare
  `Transaction(pool)` constructed in the body without `async with`
  silently leaks. The framework can't enforce.

### Option 2: `per_call=True` flag on `app.provide` (chosen)

```python
app.provide(Transaction, per_call=True)

async def transfer(tx: Transaction, src: str, dst: str, amount: int) -> None:
    await tx._conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, src)
    await tx._conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, dst)
```

The dispatcher creates a `Transaction` on the first time the call
needs it, enters it (`BEGIN`), caches it for the rest of the call,
and exits it (`COMMIT` or `ROLLBACK` based on the call outcome)
when the dispatch finishes. Exception propagation reaches
`__aexit__` exactly like a plain `async with`.

Why it wins:

- **One lifecycle model.** App-scope and per-call resources both
  arrive via DI; both clean up via the dispatcher's exit stack.
  Authors learn one pattern, reviewers check for one leak class
  (and the framework prevents that one).
- **Construction hidden behind the factory.** The body declares
  `tx: Transaction` — it does not need to know how `Transaction`
  is built. Changes to construction stay in the factory.
- **Correct path is the easy path.** Cleanup is not optional; the
  dispatcher does it. Authors can't forget `__aexit__` because
  they don't write it.
- **Exception preservation matches `async with`.** The
  `(exc_type, exc, tb)` triple forwards to `__aexit__` so
  COMMIT-on-success / ROLLBACK-on-failure works without author
  intervention. Same semantics as `async with Transaction()`.
- **Composes with `Lazy[T]`.** A per-call `Lazy[Transaction]` enters
  the transaction only if the call awaits the closure — useful
  for read-paths that branch into write-paths only sometimes.

### Option 3: No framework support — author owns everything

Acquire connection, BEGIN, commit/rollback, release — all manually.

Why it lost: every consumer reinvents the safe pattern incorrectly
the first time. The framework's job is to make the correct path the
easy path; abdicating means leaking is the default.

### Option 4: Hybrid — ship both `per_call=True` AND `async with` ergonomics

Why it lost: two ways to do the same thing (CLAUDE.md core
principle 2). Authors learn both, reviewers check both, lint rules
proliferate. The marginal author who prefers explicit `async with`
can still get it — they decline to use DI and write the resource
manually, accepting that they're outside the framework's safety net.
But this is not a shipped framework pattern; it is what the framework
does *not* prevent.

## The decision

`app.provide(T, factory, per_call=True)` is the canonical way to
declare a resource whose lifecycle is one tool dispatch. The
dispatcher:

1. Constructs the instance via the factory when the call first
   needs it.
2. Calls `__aenter__` on the instance.
3. Threads the entered instance through the call (cached for any
   re-resolutions within the call).
4. Calls `__aexit__` with `(exc_type, exc, tb)` when the call
   completes (or raises). Sibling cleanups still run even if one
   `__aexit__` raises.

There is **no** framework-shipped pattern for "use `async with` in
the body for per-call lifecycle." Authors who do so are outside the
DI scope model and own correctness themselves.

### Scope rules (related, captured here)

- A per-call resource MAY depend on app-scope resources (chain up
  to the parent container). `Transaction` depending on
  `ConnectionPool` is the canonical case.
- An app-scope resource MUST NOT depend on per-call resources. The
  framework rejects this at `async with app:` with a clear scope
  violation. Per-call types live for one dispatch; an app-scope
  instance would cache a stale per-call value. Authors who hit
  this should use `Lazy[T]` (ADR 0008) to defer resolution into
  the call scope.

## Consequences

### Positive

- One lifecycle model for resources, regardless of scope. Less to
  teach, less to review, fewer leak classes.
- Transactions are correct by construction — COMMIT/ROLLBACK
  semantics follow from exception propagation, no author work.
- Tool bodies stay focused on business logic. The `async with`
  boilerplate vanishes.
- Composes with `Lazy[T]` (zero-cost when unused per-call
  resources are declared) and factory injection (a per-call
  resource's factory can declare its own dependencies, including
  app-scope ones).

### Negative

- A second mode flag on `app.provide` (alongside the default
  app-scope). Authors must learn when to set it. The pattern doc
  and this ADR carry the rule.
- Authors expecting the FastAPI-style `Depends(get_db)` pattern
  will look for it and not find it. `per_call=True` is the same
  intent at a different declaration site (factory registration,
  not parameter annotation).
- The scope-direction rule (per-call may depend on app-scope,
  never the reverse) is a learned constraint. The framework
  enforces it at `async with app:`; the error is clear, but the
  rule exists.
- No way to declare a resource with a *custom* scope (e.g. "lives
  for one HTTP request" inside a tool that handles batches). a2kit
  has two scopes (app, per-call) and that is the surface. If a
  third scope becomes load-bearing, revisit with a follow-up ADR.

## References

- `docs/patterns/transactions.md` — usage tutorial (how-to layer
  this ADR backs).
- `src/a2kit/packages/di/` — the container implementation; the
  per-call flag and the cleanup-stack behaviour live here.
- ADR 0008 — `Lazy[T]` for conditional dependencies. Composes with
  `per_call=True` (a `Lazy[Transaction]` enters only if awaited).
- ADR 0006 — composition-root re-registration for test overrides.
  Per-call factories override the same way as app-scope.
- CLAUDE.md core principle 2 — "no multiple ways of doing the same
  thing." Rejects Option 4 (hybrid).
