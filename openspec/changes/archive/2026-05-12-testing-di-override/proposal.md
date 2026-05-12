## Why

Round-6 a2web feedback flags ~15 monkeypatch sites that reach into DI-resolved singletons to swap fakes for tests, e.g. `monkeypatch.setattr(state.llm_extractor, "_extractor", fake)  # type: ignore[assignment]`. The pattern is fragile (relies on private attribute names), type-unsafe (`# type: ignore` everywhere), and leaks across tests when the same App instance is reused. a2kit already exposes `a2kit.testing.peek(app, T)` for read-side container introspection — the missing complement is a write-side override that swaps the resolved instance for the lifetime of a single test, with auto-restore.

## What Changes

- Add `TestClient.override(type_: type[T], fake: T) -> None` on the in-process test client returned by `a2kit.testing.client(app)`. Callable any number of times before or between `invoke(...)` calls inside the same `async with` block.
- Scope: overrides are applied to the App's container on `__aenter__` (or on first `override` call), and **fully restored** on `__aexit__`. Snapshot-and-restore semantics — no permanent mutation of the App's container across tests.
- Supports both DI paths:
  - **Singletons** (`app.singleton(T, ...)` / `Container.register_singleton`): the fake replaces the cached singleton value; subsequent `peek(app, T)` and DI-injected resolutions of `T` return the fake.
  - **Providers** (`app.provide(T, ...)` / `Container.register`): the provider is shadowed by a constant-factory pinned to the fake, so every per-call `resolve(T)` returns the same fake instance for the duration of the override.
- Type-safe signature: `override[T](self, type_: type[T], fake: T) -> None` — `T` is inferred from `type_`, `fake` is bound to the same `T`. Callers get an arg-type error without needing `# type: ignore`.
- Auto-cleanup on `async with` exit, including on exception, restores the pre-test container state. Concurrent TestClients on the same App raise `RuntimeError` from `override(...)` (overrides are not concurrency-safe on a shared container; see design).
- Documentation: README/testing section gains a short "Overriding dependencies in tests" subsection with the canonical example replacing the monkeypatch pattern.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `in-process-test-client`: adds the `TestClient.override(T, fake)` requirement (scope, type safety, singleton + provider coverage, auto-restore).
- `di-container-package`: adds a small `Container` surface for snapshot/restore of singletons and providers, used exclusively by the test client (not part of the production-facing public surface beyond what `override` needs).

## Impact

- **Code touched** (implementation phase, out of scope for this proposal): `src/a2kit/packages/testing/client.py` (add `override`, snapshot bookkeeping), `src/a2kit/packages/di/container.py` (add `snapshot()` / `restore()` or equivalent narrow helpers).
- **Public API**: new method `TestClient.override`. No breaking changes.
- **Consumers**: a2web can replace ~15 monkeypatch sites; `# type: ignore[assignment]` markers go away. Pattern documented for future consumers.
- **Existing requirements unaffected**: `peek`, capture surfaces, lifecycle, `render_as`, `tools()`, `null_context` all continue to behave as specified.
