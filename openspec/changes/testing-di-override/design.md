## Context

The in-process test client (`a2kit.testing.client(app)` → `TestClient`) already runs the production dispatch path: same DI hook, same context wiring, same formatter. It exposes `peek(app, T)` (read-side) for assertions about resolved instances. Consumers (a2web in particular) still reach into resolved objects via `monkeypatch.setattr(state.foo, "_bar", fake)  # type: ignore[assignment]` to inject test doubles. That pattern:

1. depends on private attribute names (`_extractor`, etc.) — breaks silently when internals are renamed,
2. forces `# type: ignore[assignment]` because `_bar` is typed as the real type, not a Protocol/abstract type compatible with the fake,
3. mutates a singleton in place — leaks across tests when the same App instance is reused (the App is composition-root, so reuse is the norm).

The container (`a2kit.packages.di.container.Container`) is **synchronous** and **feature-agnostic**. It holds two dicts: `_providers: dict[type, Factory]` (per-call producers) and `_singletons: dict[type, Any]` (cached instances; unresolved entries carry a `_UNRESOLVED` sentinel). Both are appropriate snapshot targets.

## Goals / Non-Goals

**Goals:**
- Replace the monkeypatch pattern with a typed, scoped, dispatcher-aware override API.
- Zero `# type: ignore` at the call site.
- Auto-restore on `async with` exit (including exceptional exit).
- Cover both singleton and provider registrations uniformly.
- Composes with existing `peek` (`peek(app, T)` after `override(T, fake)` returns `fake`).
- Keep `Container` feature-agnostic — no `# test-only` branches in resolution logic.

**Non-Goals:**
- Production-time dependency swapping (e.g. feature flags). `override` is test-only and documented as such.
- Concurrency-safe overrides across multiple simultaneous `TestClient`s sharing the same App. The contract is single-test-at-a-time per App.
- Partial / attribute-level overrides (`override(T, "_bar", fake)`). The unit of substitution is the whole instance — callers pass a fake object that satisfies the registered type.
- Async factories or async fake construction. Fakes are passed in already constructed.
- Per-`invoke(...)` scoping. The scope is the whole `async with` block; calling `override` multiple times for the same `T` replaces the previous fake (last-write-wins) within the block.

## Decisions

### 1. Where `override` lives: on `TestClient`

**Choice:** `client.override(T, fake)` — instance method on the object returned by `a2kit.testing.client(app)`.

**Why:**
- Chains naturally with the existing `async with` lifecycle — the TestClient already owns enter/exit, so it is the natural owner of "snapshot on enter, restore on exit".
- Scope is unambiguous from the call site: anything inside the `async with` sees the override; anything outside does not.
- Symmetric with capture surfaces (`client.events`, `client.invoke(...)`): all test concerns route through the same object.

**Rejected:**
- `app.testing.override(T, fake)` (b) — would require an `App.testing` namespace, dragging test scaffolding onto the production App. Worse: scope is unclear without an enter/exit pair.
- `a2kit.testing.override(app, T, fake)` standalone (c) — viable but loses the auto-cleanup; the caller has to remember to undo. The whole point is to be safer than the monkeypatch pattern.

### 2. Snapshot semantics on `Container`

**Choice:** Add two narrow methods to `Container`:
- `_snapshot() -> _ContainerSnapshot` (private, test-client-only): returns a frozen record `{providers: dict[type, Factory], singletons: dict[type, Any]}` — shallow copies of the two dicts.
- `_restore(snapshot: _ContainerSnapshot) -> None`: replaces `_providers` and `_singletons` with the snapshot's contents.

Both are sync, feature-agnostic, and prefixed with `_` so they do not enlarge the documented public surface defined by the `di-container-package` spec ("Public surface is small and synchronous: `register`, `has`, `providers`, `resolve`, `apply_kwargs`, `partition_kwargs`, `allowlist`, `has_allowlisted`"). The spec needs a small amendment to permit a test-only snapshot/restore pair without contradicting "public surface is small".

**Rejected:**
- "Pin overrides into a separate `_overrides` dict and consult it in `resolve`." That would add a feature-aware branch (`if type_ in self._overrides`) to hot-path resolution. Snapshot/restore keeps resolution untouched.

### 3. How `override` mutates the container

```python
def override(self, type_: type[T], fake: T) -> None:
    if self._snapshot is None:
        self._snapshot = self.app.container()._snapshot()
    c = self.app.container()
    if type_ in c._singletons or c.has(type_):
        # Pin the singleton cache to the fake AND pin the provider to a constant
        # factory returning the same fake. The first covers `peek` and any
        # singleton-fast-path resolves; the second covers fresh resolves
        # in case the type was registered as a per-call provider, not a singleton.
        c._singletons[type_] = fake
        c._providers[type_] = lambda: fake
    else:
        # Type not registered at all — register fresh as a singleton-equivalent.
        c._singletons[type_] = fake
        c._providers[type_] = lambda: fake
```

Restoration: `c._restore(self._snapshot)` on `__aexit__`. The snapshot is captured **once** per TestClient session (on first `override` call, not on `__aenter__`) so a TestClient that never calls `override` pays zero cost.

### 4. Type-safe signature

```python
from typing import TypeVar
T = TypeVar("T")

class TestClient:
    def override(self, type_: type[T], fake: T) -> None: ...
```

mypy / pyright / ty infer `T` from `type_` and bind `fake` to the same `T`. Calling `client.override(LLMExtractor, FakeLLM())` where `FakeLLM` is not assignable to `LLMExtractor` produces an error at the call site without any `# type: ignore`. Consumers commonly define a `Protocol` or abstract base for the dependency and register the production class against it — that pattern continues to work, with `T = ProtocolType`.

**Rejected:**
- `override[T](T, fake)` PEP 695 generic-method syntax — works on Python 3.12+ but a2kit targets 3.11; classic `TypeVar` is the portable form. Semantically equivalent.

### 5. Interaction with `peek`

`peek(app, T)` is documented as `app.container().resolve_sync(type_)`. Because `override` pins both the singleton cache slot and the provider, `peek` returns the fake after override — no special case needed in `peek`'s implementation. This is the test invariant: **after `client.override(T, fake)`, both `peek(app, T)` and any DI-injected `T` inside `invoke(...)` return `fake`.** The specs encode this as scenarios.

### 6. Concurrency

The Container is not thread-safe; the App is single-test-at-a-time by contract. Two TestClients entered concurrently on the same App would corrupt each other's snapshots. We guard with a simple flag on the App (e.g. `app._test_override_owner: TestClient | None`); `override` raises `RuntimeError("App already has an active override session from another TestClient")` if the flag is held by another TestClient. The flag is cleared on `__aexit__`.

For per-test isolation, the recommended pattern remains: construct the App fresh per test (pytest fixture), or rely on snapshot/restore — both are documented.

## Risks / Trade-offs

- **[Risk] Hidden coupling to container internals (`_singletons`, `_providers`).** → Mitigation: `_snapshot` / `_restore` are sealed test-only helpers on `Container`. The spec amendment makes this explicit. No other module reaches into the underscored dicts.
- **[Risk] Override leaks if `__aexit__` is skipped (e.g., test runner crash mid-test).** → Mitigation: documented limitation. Same risk as any context-manager-scoped resource. Pytest fixtures recommended.
- **[Risk] Fake doesn't satisfy the registered type at runtime, only at type-check time (duck-typing).** → Acceptable; matches the existing monkeypatch behavior and Python idiom. Pyright/ty catches mismatches at the call site.
- **[Risk] Singleton with eager init (factory already ran, instance held by long-lived consumer).** → If a consumer captured a reference to the pre-override singleton before `override` was called, that reference is not retroactively swapped. Same caveat as monkeypatch. Test pattern: call `override` **before** the first `invoke(...)` that would resolve `T`.
- **[Trade-off] Snapshot/restore copies the two dicts (shallow). O(N) in registered types per session.** Cheap (tens to low hundreds of providers in practice).
