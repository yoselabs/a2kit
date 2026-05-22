# Test overrides — composition-root re-registration

a2kit's DI container has no dedicated `override(T, fake)` test seam.
Test overrides happen at the composition root by re-registering the
type on an `AppBuilder`. The builder's `provide()` is
**last-write-wins**: a second registration silently replaces the prior
factory. `build()` then seals the result into a runtime `App`.

```python
def build_app(*, llm: LLM | None = None) -> a2kit.App:
    builder = a2kit.AppBuilder("prod")
    builder.provide(Settings)
    builder.provide(LLM, lambda: llm or OpenAILLM())
    builder.provide(Repo)
    return builder.build()

def build_test_app(*, llm_fake: LLM, repo_fake: Repo | None = None) -> a2kit.App:
    builder = a2kit.AppBuilder("prod")
    builder.provide(Settings)
    builder.provide(LLM, lambda: llm_fake)
    # Re-register to override — last-write-wins, pre-build().
    builder.provide(Repo, lambda: repo_fake or Repo())
    return builder.build()
```

```python
@pytest.mark.asyncio
async def test_extract_uses_fake_llm():
    app = build_test_app(llm_fake=StubLLM(canned="hello"))
    async with app:
        async with app._resolver.dispatch(extract, {"url": "x"}) as kw:
            result = await extract(**kw)
    assert result == "hello"
```

## Why no `override()` method?

- One registration API to teach and to lint. `provide()` does the job
  on its own.
- Composition-root overrides keep test wiring visible at the call
  site. A reader of `build_test_app` sees the full graph without
  having to chase an `override` table.
- No special sealing exception. `AppBuilder.build()` seals the
  container; an override after `build()` is impossible because the
  sealed `App` has no `provide`. The builder/runtime split (ADR 0016)
  makes "override after seal" a type error, not a runtime raise.

A dedicated `TestClient.override()` existed once and was removed in
v0.40: it mutated an already-sealed container, contradicting ADR 0006.
Calling it now raises a migration hint pointing here.

## Common patterns

**Stub a single dependency** — provide the fake last on the builder:

```python
builder.provide(LLM, lambda: StubLLM())
```

**Stub a class via factory**:

```python
builder.provide(LLM, lambda: StubLLM(canned=fixture_payload))
```

**Stub a per-call resource**:

```python
builder.provide(Transaction, lambda pool: InMemoryTransaction(pool), per_call=True)
```

The factory's parameter annotations chain through DI normally — the
override receives its own dependencies via the same machinery.

## Anti-pattern: mutate AFTER `build()`

Don't reach for the builder once `build()` has run. It is spent, and
the `App` it produced is sealed:

```python
app = builder.build()
builder.provide(LLM, lambda: StubLLM())  # TypeError — builder is spent
app.provide(LLM, lambda: StubLLM())      # TypeError — App has no provide
```

If you need per-test isolation: build a fresh `App` from a fresh
`AppBuilder` per test. Composition is cheap; reset is loud.
