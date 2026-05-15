## Why

a2web's v0.38 friction inventory (`A2KIT_FEEDBACK_v0.38.md`, frictions
A1 + A2) identified two test-harness helpers that every consumer
reinvents in `conftest.py`:

1. **`lazy_of(value)`** — wraps a pre-built fake into the
   `Lazy[T] = Callable[[], Awaitable[T]]` shape expected by tool
   kwargs declared with `Lazy[T]`. Five lines, identical across
   consumers.
2. **`_ambient_ldd` autouse fixture** — establishes
   `ldd_state_for_call(ctx=null_context(), events_enabled=False,
   reports_enabled=False)` so tests that call orchestrator / phase
   functions directly (bypassing `TestClient.invoke`) don't crash
   with `AmbientContextMissing`. Universal pattern for any consumer
   with phase functions that emit LDD events.

Both are pure ergonomic wins — no new framework behavior, no
contract changes. Ship them on the existing `a2kit.testing.*`
surface (already exposes `client`, `peek`, `null_context`,
`cassette`, `compute_schema`, `app`).

### What we are NOT doing

a2web also asked for `await a2kit.testing.resolve(app, T)` (A3) —
parked. Resolving a type outside a dispatch enters resources via
`__aenter__`; the free-function signature in the ask doesn't say
where they get torn down. Per-call lifecycle stack is the v0.36
invariant. A scope context-manager (`resolution_scope`) is the
likely shape but needs design work; not bundled here.

The "silent no-op outside dispatch" alternative for A2 is also
**rejected** — it inverts the loud-by-default contract that
`AmbientContextMissing` exists to enforce (principle 3 in
`CLAUDE.md`). The fixture form preserves the contract while giving
consumers the ergonomics.

## What Changes

### `a2kit.testing.lazy(value)` constructor

- Add `a2kit.testing.lazy` — synchronous constructor that takes any
  value and returns a zero-arg async callable matching
  `Lazy[T]` (`Callable[[], Awaitable[T]]`).
- Implementation: factory closure that returns `value` unchanged.
  No deepcopy, no caching layer — `Lazy[T]` is already a thunk;
  callers who want fresh values per call build their own.
- Add to `a2kit.testing.__all__`. **Do not** add `Lazy.of` — `Lazy`
  is a `TypeAlias`, not a runtime class.

### `a2kit.testing.ambient_for_tests` pytest fixture

- Add `a2kit.testing.ambient_for_tests` — a `@pytest.fixture` that
  wraps test execution in `ldd_state_for_call(ctx=null_context(),
  events_enabled=False, reports_enabled=False)`.
- Ship as a **named fixture** (not autouse-by-default). Consumers
  opt in either by listing it in `pytest_plugins` and re-exporting
  with `autouse=True` in their `conftest.py`, or by depending on it
  per-test.
- The fixture SHALL be importable as
  `from a2kit.testing import ambient_for_tests`; pytest discovers it
  via the standard fixture-import path.
- Default flags match the inventory ask: events disabled, reports
  disabled, ctx = `null_context()`. Consumers who want a different
  shape build their own fixture using `ldd_state_for_call` directly
  — this fixture is the 95% case, not a kitchen sink.

### Documentation

- Update `docs/patterns/` (or equivalent) with a "Testing helpers"
  section showing both helpers.
- Add a migration note: consumers can delete `lazy_of` and the
  autouse `_ambient_ldd` fixture from their `conftest.py` once they
  upgrade.

## Out of scope

- A3 `resolve(app, T)` — needs scope CM design.
- Friction B (`Router.emits_ldd` marker) — separate proposal.
- Friction F (`Resource.warm_up()`) — spike + doc first.
- Renaming `null_context` / restructuring `a2kit.testing` surface.

## Impact

- **`a2kit.testing` surface** — two new public symbols. Cap on
  top-level `a2kit.*` namespace is unchanged.
- **Spec** — `in-process-test-client` capability gains two new
  requirements.
- **No deprecations.** Consumer-local `lazy_of` helpers continue to
  work; they're just redundant. No loud-crash needed since this
  surface was never framework-owned.
