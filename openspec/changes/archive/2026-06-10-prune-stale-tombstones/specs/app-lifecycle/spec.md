## REMOVED Requirements

### Requirement: `App.__init__` SHALL reject the removed `lifespan=` kwarg with a migration hint

**Reason**: `lifespan=` was removed in v0.35 — well past the migration horizon. Under the tombstone sunset rule (`AGENTS.md` §1), the bespoke hint is swept. `App.__init__` still accepts `**_kw` and rejects unknown kwargs with the standard "unexpected kwarg" `TypeError` (naming the offending kwarg + the CHANGELOG), spec'd by `core-purity`; `lifespan` now falls through to that generic path.

**Migration**: none — `App(lifespan=...)` still raises a loud `TypeError`, the generic unknown-kwarg one rather than a `lifespan`-specific hint. The replacement (a marker resource with `__aenter__`/`__aexit__`, or imperative work in `main()` before `async with app:`) is recorded in the CHANGELOG.
