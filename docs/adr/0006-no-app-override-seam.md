---
id: "0006"
status: accepted
date: 2026-05-18
last_reviewed: 2026-05-18
supersedes: []
superseded_by: null
tags: [di, testing, surface]
deciders: [Denis Tomilin]
---

# ADR 0006: No dedicated `app.override(T, fake)` test seam

## Status

Accepted, 2026-05-18. Backfilled — the decision was settled in v0.36
when the DI container shipped; this ADR records the rationale that
previously lived only in `docs/patterns/test-overrides.md`.

## Summary

In the context of test wiring against a2kit's DI container, facing
the question of how authors should swap real services for fakes in
tests, we decided to ship no dedicated `app.override(T, fake)`
method and rely instead on composition-root re-registration (the
container's `provide()` is last-write-wins, so a second call before
`__aenter__` silently replaces the prior factory), to achieve a
single registration API to teach and to lint and test wiring that
stays visible at the composition root, accepting that authors must
factor their composition as a function (`build_app(*, llm=None)`)
to admit overrides, and that there is no in-context override after
`async with app:` because the container is sealed at that point.

## The problem

A2kit's DI container is built around `app.provide(T, factory)`. Tests
need to swap real services for fakes — a `StubLLM` instead of
`OpenAILLM`, an `InMemoryRepo` instead of `PostgresRepo`. Every Python
DI library has to answer "how do tests override?" and the answers
fall on a spectrum:

- **Dedicated override method.** `app.override(T, fake)` — pytest-style
  monkey-patching, a separate registration path tracked separately
  from production wiring. Common in fastapi (`app.dependency_overrides`),
  dependency-injector (`provider.override()`), wired (`Container.override()`).
- **Re-registration.** A second `provide()` call wins. No separate
  API; tests use the same primitive as production wiring.
- **Mock at use site.** Patch the import / attribute / module. Doesn't
  compose with DI machinery; only works for module-level globals.

A2kit had to choose between option 1 and option 2 when v0.36 shipped
the lazy-CM-aware container. The natural reading of the existing
`provide()` semantics (last-write-wins, seal-on-enter) made option 2
already work without any additional API. The question was: should we
*also* ship an explicit `override()` for ergonomics?

The reasonable contributor reading the codebase would ask: "Why isn't
there an `app.override()` method? Every other DI library has one."
Without a recorded answer, that question recurs every time a new
contributor — or AI agent — examines the test seam.

## What we considered (and why this one)

### Option 1: Ship `app.override(T, fake)` as a dedicated test seam

The fastapi / dependency-injector pattern. A separate method,
tracked in a separate dict, applied during dispatch in addition to
the production registrations. Tests use `app.override(LLM, StubLLM())`
without touching `build_app`.

Why it lost:

- **Two registration APIs to teach.** Authors now have to learn both
  `provide()` (production) and `override()` (testing), and remember
  when to use which. The lint rule "did you mean `override` here?"
  becomes a real concern; the framework grows surface that doesn't
  earn its keep.
- **Hidden wiring.** The override table is global state attached to
  the container. A reader of `build_test_app(...)` sees the
  production graph but not the overrides — those live in a `setUp`
  or fixture somewhere. Composition becomes spooky-action-at-a-distance.
- **Sealing exception.** The container seals at `__aenter__`. An
  `override()` API has to choose: either it also rejects post-seal
  calls (then it's just re-registration with extra steps), or it
  allows post-seal overrides (then the seal is a lie and the
  container's lifecycle invariants weaken). Neither is good.
- **No real ergonomic win.** Composition-root re-registration is one
  line per override; `override()` is one line per override. Same
  cost, more API.

### Option 2: Composition-root re-registration (chosen)

Tests factor their composition as a function with override
parameters, and pass fakes at construction. The same `provide()`
calls happen, just with different factories.

```python
def build_app(*, llm: LLM | None = None) -> a2kit.App:
    app = a2kit.App("prod")
    app.provide(Settings)
    app.provide(LLM, lambda: llm or OpenAILLM())
    app.provide(Repo)
    return app

def build_test_app(*, llm_fake: LLM, repo_fake: Repo | None = None) -> a2kit.App:
    app = build_app(llm=llm_fake)
    if repo_fake is not None:
        app.provide(Repo, lambda: repo_fake)
    return app
```

Why it wins:

- **One registration API.** `provide()` does production wiring AND
  test overrides. Same lint rules, same teaching surface, same
  mental model.
- **Test wiring is visible at the call site.** A reader of
  `build_test_app` sees the full graph including the overrides. No
  separate table to chase.
- **No sealing exception.** Overrides land BEFORE `__aenter__`, just
  like production wiring. The seal stays absolute.
- **Composition root as a function falls out for free.** Authors
  factoring their app as `build_app(*, ...)` get clean per-test
  isolation by construction (each test calls `build_app()` again).
  This is good design hygiene independent of testing.

### Option 3: Hybrid — `app.override()` with explicit pre-seal semantics

A method that internally just calls `provide()` again. Pure sugar.

Why it lost: by reduction, this is option 1 with a marketing name. It
still creates a second-way-to-do-the-same-thing (CLAUDE.md core
principle 2). If `override()` does nothing `provide()` cannot, it
should not exist.

## The decision

A2kit's DI container ships **no** `app.override(T, fake)` method.
Tests override by:

1. Factoring composition as `build_app(*, ...)` with override kwargs.
2. Re-calling `app.provide(T, fake_factory)` at the composition root
   if the override is finer-grained than a kwarg captures.

Both happen BEFORE `async with app:`. The container seal at
`__aenter__` remains absolute: post-seal `provide()` raises
`TypeError`.

The pattern is documented in `docs/patterns/test-overrides.md`
(usage / how-to). This ADR is the rationale layer (why no dedicated
method).

## Consequences

### Positive

- One registration API on the container. Authors and AI agents learn
  one primitive (`provide()`) and apply it everywhere — production
  wiring, test overrides, per-call resources, eager singletons. Less
  surface to teach, lint, and document.
- Test composition graphs are statically readable. A reader does not
  need to know about a parallel override table; the function
  signature of `build_test_app` carries the full override list.
- The container's sealing semantics stay simple and absolute. No
  carve-out for "overrides that land after the seal."
- Encourages factoring the composition root as a function, which is
  good practice for application code independent of testing.

### Negative

- Authors who land on a2kit from fastapi or dependency-injector will
  look for `app.override()` and not find it. Without this ADR, the
  question recurs for every new contributor. With it, the answer is
  one paragraph and a citation.
- Composition-root re-registration is slightly more code than
  `app.override(T, fake)` would be in trivial cases. The trade-off
  buys visibility and a smaller API surface; in our judgment that is
  worth ~3 lines per test fixture.
- No way to override *inside* a test after `async with app:` opens
  the container. If a test genuinely needs mid-flight override, it
  must build a second app — the doctrine is "composition is cheap,
  reset is loud." This is sometimes inconvenient (e.g. switching
  the LLM mid-test to assert a behaviour change). Authors who need
  that pattern factor their tests into two `async with` blocks.

## References

- `docs/patterns/test-overrides.md` — usage patterns, examples,
  anti-patterns. The how-to layer that this ADR backs.
- `CLAUDE.md` core principle 2 — "no multiple ways of doing the same
  thing." Directly motivates rejecting Option 1.
- `src/a2kit/packages/di/` — the DI container implementation;
  `provide()` semantics live here. The last-write-wins behaviour is
  the structural fact this ADR builds on.
