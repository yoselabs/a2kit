# app-lifecycle — explicit-router-surface delta

## ADDED Requirements

### Requirement: `App.add_router(r)` composes `r.lifespan` into the App's top-level lifespan

`App.add_router(r)` SHALL compose `r.lifespan` (when defined as a
`@contextlib.asynccontextmanager async def lifespan(self):` method
on the Router subclass) into the App's top-level lifespan via
`a2kit.lifespan.compose(...)` — the helper introduced by the
sibling `lifespan-over-lifecycle-hooks` proposal.
The pre-`yield` body of each Router's `lifespan` SHALL run during
the App's startup phase before any tool dispatch is served; the
post-`yield` body SHALL run during the App's shutdown phase after
all in-flight tool dispatch has completed.

Composition order SHALL be: the App's own lifespan first, then each
Router's lifespan in `add_router` registration order.

This delta is **narrowly scoped** to the Router-composition rule.
The broader `App.lifespan=` surface — replacing `@app.on_startup` /
`@app.on_shutdown` with an `asynccontextmanager` — is owned by the
sibling `lifespan-over-lifecycle-hooks` proposal and SHALL NOT be
duplicated here. Both proposals ship paired in v0.31.0.

#### Scenario: Router lifespan runs at App startup and shutdown

- **GIVEN** an `App` with a Router whose `lifespan` opens a store
  before `yield` and closes it after
- **WHEN** the App's top-level lifespan is entered (server start)
  and later exited (server shutdown)
- **THEN** the Router's pre-`yield` body runs before tool dispatch
  begins, and its post-`yield` body runs after the last tool
  dispatch completes

#### Scenario: Multiple Routers compose in registration order

- **GIVEN** an `App` to which `RouterA` is added before `RouterB`,
  each with its own `lifespan`
- **WHEN** the App's lifespan starts
- **THEN** `RouterA.lifespan`'s pre-`yield` body runs before
  `RouterB.lifespan`'s pre-`yield` body
- **AND** at shutdown, `RouterB.lifespan`'s post-`yield` body runs
  before `RouterA.lifespan`'s post-`yield` body (LIFO unwind, as
  guaranteed by `a2kit.lifespan.compose`'s `AsyncExitStack`
  semantics)
