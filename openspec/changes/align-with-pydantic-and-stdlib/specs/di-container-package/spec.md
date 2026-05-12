# di-container-package — align-with-pydantic-and-stdlib delta

## ADDED Requirements

### Requirement: Container parameter cache uses `WeakKeyDictionary`

The `Container`'s per-factory parameter introspection cache SHALL be
a `weakref.WeakKeyDictionary` keyed on the factory object itself,
NOT a `dict` keyed on `id(factory)`. The `id(factory)` keying
pattern is forbidden because CPython recycles `id` values when
refcount drops to zero; in nested scopes a discarded factory's id
may be reused by a later registration, producing stale cache hits
with the wrong `_ParamSpec` list applied at resolve time. The same
failure mode is documented in `src/a2kit/signature.py`'s design
note for tool-signature caching; the container SHALL adopt the
weak-keyed shape that already proved itself there.

When a factory is garbage-collected, its cache entry SHALL vanish
without requiring any explicit cleanup call.

If a registered factory is not weak-referenceable (e.g.
`functools.partial`), the cache write SHALL raise `TypeError` at
`register()` time with a message naming weak-referenceability as
the cause and recommending a `def`-bound wrapper. The container
SHALL NOT silently fall back to a no-cache path — the loud failure
is the contract.

#### Scenario: Stale-id aliasing cannot produce a stale cache hit

- **GIVEN** a Container into which `def f(...)` is registered as a
  factory and then `f` goes out of scope and is garbage-collected
- **WHEN** a second factory `def g(...)` is later registered whose
  CPython `id` happens to equal the recycled id of `f`
- **THEN** the container's parameter cache returns the
  `_ParamSpec` list inferred from `g`, never the stale list from
  `f` — because keys are the live function objects, not their ids

#### Scenario: Cache entry vanishes on factory GC

- **GIVEN** a factory `f` registered with the Container and its
  parameter cache entry populated by a prior resolve
- **WHEN** every strong reference to `f` is dropped and a GC cycle
  runs
- **THEN** the Container's `_param_cache` no longer contains an
  entry for `f` (or for any object whose identity equals the
  GC'd `f`)

#### Scenario: Non-weak-referenceable factory raises at registration

- **GIVEN** a `functools.partial(some_func, arg)` value passed as
  the factory to `Container.register(SomeType, factory=...)`
- **WHEN** the container attempts to populate the parameter cache
- **THEN** `TypeError` is raised with a message that names weak
  references and points the caller at the `def`-wrapper workaround
