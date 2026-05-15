## Why

a2web's v0.38 friction inventory (`A2KIT_FEEDBACK_v0.38.md`,
Friction F) flagged that their `@app.health_check` body calls
`await sqlite._ensure()` — poking an underscore-prefixed internal
method on a consumer-side `SqliteResource`. The body comment
explains: "the framework *should* have entered the resource via
`__aenter__` already, but we call `_ensure()` as belt-and-suspenders
because the contract isn't documented."

The question was concrete: **does kwarg resolution inside a
`@app.health_check` function trigger `__aenter__` on the resolved
resource?**

**Resolved by reading-only spike on 2026-05-15: YES.** Trace:

```
run_checks (packages/health/__init__.py:74)
  └─ _run_one_check (line 100)
      └─ app._container.resolve_params(check.fn)        (line 108)
          └─ Container.get(T) per kwarg
              └─ _construct                              (container.py:507)
                  └─ _enter_lifecycle                    (line 530)
                      └─ resource.__aenter__()           (di/_helpers.py:84)
                          + cleanup recorded on root or
                            child cleanup stack
```

The `_run_one_check` docstring already documents this:
*"Routes through the v0.36 resolver so app-scope `__aenter__`
runs on first resolution (lazy first-use). Health checks
declaring a resource as a parameter trigger entry of that
resource."* (lines 104-107).

The contract is real but lives only in an internal docstring. This
change promotes it to a capability requirement so a2web (and any
future consumer) can rely on it without reading the source.

### Important nuance the spike uncovered

The first version of this change's spec delta said `__aexit__`
fires when "the health-probe dispatch completes." **That was
wrong.** Resources resolved by the health-check path follow the
standard DI scope rules:

- **SINGLETON** (the default for `app.singleton(...)`) — entered
  on first resolution **anywhere in the app**, exited at app
  shutdown via `Container.aclose()`.
- **SCOPED** (per-call) — entered per dispatch, exited at end of
  dispatch.

a2web's `SqliteResource` is almost certainly a singleton. So the
"resource is ready" guarantee at the start of the check body is
real, but the resource may have been entered hours earlier by a
tool dispatch — not by this specific health probe. The contract is
"entered before your check body runs," not "entered by your check."

The `await sqlite._ensure()` belt-and-suspenders call is redundant
either way. The spec delta below captures the precise semantics
including singleton-vs-scoped behaviour.

## What Changes

This is a **doc-only** change. No code, no new API.

### Spec — `health-probe` capability

- ADD requirement: `@app.health_check` kwargs route through
  `Container.resolve_params`, same as tool dispatch. Resources
  enter via `__aenter__` on first resolution; exit follows the
  scope (SINGLETON exits at app shutdown, SCOPED exits at end of
  dispatch).
- ADD scenarios: first probe enters singleton; second probe
  reuses cached singleton (no re-entry); singleton exits at app
  shutdown not per probe; failure path doesn't affect lifecycle;
  shared singleton across checks enters once. See
  `specs/health-probe/spec.md`.

### Documentation

- Add a new Q to `OPERATIONAL_CONTRACTS.md`: *"Does
  `@app.health_check` kwarg resolution enter resources?"* — answer:
  yes, via the standard DI path; SINGLETON resources may be
  entered before the probe (by an earlier tool dispatch or a prior
  probe), so the probe receives a ready resource but is not always
  the call that triggered the entry.
- Verify the contract by adding a focused test
  `tests/test_health_check_resource_entry.py` with a `SpyResource`
  asserting the SINGLETON semantics (one entry across N probes,
  exit at lifespan unwind).
- Update `CHANGELOG.md` `Unreleased` under "Documented" (or
  "Clarified" — verify existing section headers).

## Out of scope

- `Resource.warm_up()` primitive — not needed. The DI resolver
  already enters resources via `__aenter__`. Adding `warm_up()`
  would duplicate `__aenter__` semantics (principle 2 violation).
- Changing tool-dispatch resource-entry semantics — already works
  correctly; no change.
- Forcing per-probe re-entry of SINGLETON resources — that would
  break the singleton contract. The probe-receives-a-ready-resource
  guarantee is sufficient.
- Health-check ergonomics changes (e.g. `@app.health_check` taking
  parameters other than DI kwargs).

## Impact

- Doc-only. Zero consumer-visible surface change.
- a2web's consumer fix: drop `await sqlite._ensure()` lines from
  health-check bodies. The resource is already entered by the
  resolver.
- One test added (`tests/test_health_check_resource_entry.py`)
  that pins the behaviour against future refactors.
