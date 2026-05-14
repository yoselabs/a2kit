# Test overrides — composition-root re-registration

In v0.36 the DI container has no dedicated `app.override(T, fake)`
test seam. Test overrides happen at the composition root by
re-registering the type. The container's `provide()` is
**last-write-wins**: a second registration silently replaces the prior
factory.

```python
def build_app(*, llm: LLM | None = None) -> a2kit.App:
    app = a2kit.App("prod")
    app.provide(Settings)
    app.provide(LLM, lambda: llm or OpenAILLM())
    app.provide(Repo)
    return app

def build_test_app(*, llm_fake: LLM) -> a2kit.App:
    app = build_app(llm=llm_fake)
    # Or override at the composition root:
    app.provide(Repo, lambda: FakeRepo())
    return app
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

## Why no `app.override()`?

- One registration API to teach and to lint. `provide()` does the job
  on its own.
- Composition-root overrides keep test wiring visible at the call
  site. A reader of `build_test_app` sees the full graph without
  having to chase an `override` table.
- No special sealing exception: the container seals after
  `__aenter__`, period. Overrides land BEFORE entering the App, just
  like production wiring.

## Common patterns

**Stub a single dependency**:

```python
app.provide(LLM, lambda: StubLLM())
```

**Stub a class via factory**:

```python
app.provide(LLM, lambda: StubLLM(canned=fixture_payload))
```

**Stub a per-call resource**:

```python
app.provide(Transaction, lambda pool: InMemoryTransaction(pool), per_call=True)
```

The factory's parameter annotations chain through DI normally — the
override receives its own dependencies via the same machinery.

## Anti-pattern: override AFTER `async with app:`

Don't do this. The container is sealed:

```python
async with app:
    app.provide(LLM, lambda: StubLLM())  # TypeError — container sealed
```

If you need per-test isolation: build a fresh `app` per test.
Composition is cheap; reset is loud.
