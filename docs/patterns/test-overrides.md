# Test overrides — composition-root re-registration

a2kit's DI container has no dedicated `override(T, fake)` test seam.
Test overrides happen at the composition root by re-registering the
type on the `a2kit.App`. `provide()` is **last-write-wins**: a second
registration silently replaces the prior factory. A finisher
(`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`) then seals
the App.

```python
def build_app(*, llm: LLM | None = None) -> a2kit.App:
    app = a2kit.App("prod")
    app.provide(Settings)
    app.provide(LLM, lambda: llm or OpenAILLM())
    app.provide(Repo)
    return app

def build_test_app(*, llm_fake: LLM, repo_fake: Repo | None = None) -> a2kit.App:
    app = a2kit.App("prod")
    app.provide(Settings)
    app.provide(LLM, lambda: llm_fake)
    # Re-register to override — last-write-wins, before a finisher seals.
    app.provide(Repo, lambda: repo_fake or Repo())
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

## Why no `override()` method?

- One registration API to teach and to lint. `provide()` does the job
  on its own.
- Composition-root overrides keep test wiring visible at the call
  site. A reader of `build_test_app` sees the full graph without
  having to chase an `override` table.
- No special sealing exception. A finisher seals the container; an
  override after sealing raises `TypeError`, because `provide` on a
  sealed `App` is rejected (ADR 0017).

A dedicated `TestClient.override()` existed once and was removed in
v0.40: it mutated an already-sealed container, contradicting ADR 0006.
Calling it now raises a migration hint pointing here.

## Common patterns

**Stub a single dependency** — provide the fake last on the App:

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

## Anti-pattern: compose AFTER a finisher has sealed the App

Don't reach for the App's composition verbs once a finisher has run.
The App is sealed:

```python
async with a2kit.testing.client(app):
    ...
app.provide(LLM, lambda: StubLLM())  # TypeError — App is sealed
```

If you need per-test isolation: construct a fresh `a2kit.App` per test.
Composition is cheap; reset is loud.
