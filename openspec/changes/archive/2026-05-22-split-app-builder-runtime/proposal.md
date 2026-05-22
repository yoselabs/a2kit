## Why

`App` is two objects in a trenchcoat:

- a **mutable builder** — `add_router`, `add_cli`, `add_mcp_middleware`,
  `provide`, `health_check`; legal only *before* `async with app:`.
- a **sealed runtime** — `tools()`, `container()`, `_resolver`, the
  async-CM lifecycle, the LDD kill-switch; meaningful only *after*.

The phase boundary is real (the container seals at `__aenter__` — ADR
0006) but invisible to the type system. `provide()` after the seal
raises *at runtime*; mutating wiring after entry is a runtime surprise,
not a compile error. One class carries seven-plus responsibilities and
the reader cannot tell, from a type, which methods are legal when.

A deeper review surfaced a second, sharper reason. The test-override
seam is a **distributed post-seal mutation mechanism** —
`App._test_override_owner` + `Container._override` / `_snapshot` /
`_restore` + `TestClient.override()` — that overrides an
*already-sealed* container mid-test. ADR 0006 (accepted 2026-05-18)
records the opposite: *"there is no in-context override after `async
with app:` because the container is sealed."* The code contradicts its
own four-day-old ADR. `AppBuilder` resolves this cleanly — see below.

Thread E from the architecture review — "is the core transport
neutral?" — is folded in here as a decision, because it is a question
about exactly this surface (`add_mcp_middleware` is MCP-specific).

## What Changes

- **`AppBuilder`** — the mutable composition surface: `add_router`,
  `add_cli`, `add_mcp_middleware`, `provide`, `health_check`. Terminal
  method `build() -> App`.
- **`App`** — the sealed runtime: `tools()`, `routers()`,
  `container()`, `_resolver`, the async-context-manager lifecycle, the
  LDD kill-switch. No mutating methods.
- `build()` is the seal point: it constructs the `Container`, validates
  the provider graph, auto-installs the `_meta.health` router if checks
  were registered, and returns the immutable `App`.
- `a2kit.run(...)` and `build_mcp_server(...)` accept the sealed `App`.
- Misuse crashes loud with a migration hint: `a2kit.App("name")`
  directly, or any composition verb on a built `App`, raises a
  `TypeError` naming `AppBuilder`.
- **The test-override seam is replaced by re-build.**
  `Container._override` / `_snapshot` / `_restore` /
  `_ContainerSnapshot`, `App._test_override_owner`, and
  `TestClient.override()` are **deleted**. A test that swapped a
  service mid-run instead builds a fresh `App` from an `AppBuilder`
  with the fake `provide()`d (last-write-wins, pre-`build()`). This
  removes ~50 LOC of distributed coupling and makes ADR 0006's
  recorded invariant finally true.

**BREAKING**: composition moves off `App`
(`a2kit.App("svc").add_router(r)` becomes
`a2kit.AppBuilder("svc").add_router(r).build()`). `TestClient.override()`
is removed in favor of re-build. Every `async with App(...)` site,
every example, and many tests change.

Both `AppBuilder` and `App` stay in `src/a2kit/app.py` — no new core
file (the core-file-count budget in `module-layout-discipline` is
already tight).

## Capabilities

### New Capabilities

- `app-builder-runtime`: the builder/runtime split — `AppBuilder` is
  mutable and terminal-`build()`s; `App` is the sealed, mutation-free
  runtime; test overrides are re-build, not post-seal mutation.

### Modified Capabilities

- `core-composition`: the three named composition verbs move from
  `App` to `AppBuilder`.

## Impact

- Largest blast radius of the four architecture changes — touches every
  composition site (examples, tests, README, downstream consumers).
- Misuse of the two-phase lifecycle becomes a type error / loud crash
  instead of a silent or late failure.
- Resolves the ADR 0006 code/decision divergence and deletes the
  distributed post-seal test-override seam.
- Independent of the other three changes — no ordering dependency — but
  sequenced **last** because it is the most invasive and benefits from
  a clean graph underneath.
- Higher value than the first review assumed: beyond the type-safety
  win, it reconciles a live ADR contradiction and removes a coupling
  the user's original brief explicitly targeted.
