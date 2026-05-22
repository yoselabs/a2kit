## Why

`split-app-builder-runtime` (ADR 0016, archived 2026-05-22) split the
central type into a public `AppBuilder` and a public sealed `App`. The
split exists to stop a *consumer* mutating the sealed runtime. But the
sealed runtime never needs to be a consumer-visible thing at all: a2kit
already routes every "finish" through an entry point (`a2kit.run`,
`build_mcp_server`, `testing.client`). If those entry points seal
internally, the consumer holds only the mutable object and the sealed
runtime stays inside the framework — there is no consumer to protect, so
the two public types collapse to one.

This narrows the framework⇄consumer contract to its smallest honest
form — one type, `a2kit.App`, plus the entry functions — and frees the
entire sealed-runtime mechanism (the seal point, the validation, the
runtime representation) to change without ever breaking consumer code.

## What Changes

- **The public surface is one type: `a2kit.App`.** It is constructed
  directly, carries the composition verbs (`add_router`, `add_cli`,
  `add_mcp_middleware`, `provide`, `health_check`), and is what the
  consumer holds end-to-end. **BREAKING**: `a2kit.AppBuilder` is
  removed; the name `App` now denotes the (mutable) composition object.
- **The sealed runtime becomes internal.** Sealing produces no
  consumer-visible type. Whether it is a flag on `App` or a private
  class is a framework implementation detail, explicitly outside the
  contract.
- **`build()` leaves the public surface.** **BREAKING**: there is no
  public `build()`. The entry points — `a2kit.run`, `build_mcp_server`,
  `testing.client` — accept an `App` and seal it internally (validate
  the provider graph, lock the container) before running / serving /
  testing. Consumer code never calls a seal step.
- **Composition after a finisher has sealed the App raises** `TypeError`
  loud-crash — a same-object misuse, caught at runtime.
- The post-seal test-override seam stays deleted (carried unchanged
  from `split-app-builder-runtime`). Test overrides remain re-build:
  construct a fresh `App`, `provide` the fake (last-write-wins).
- **BREAKING**: every composition site migrates back —
  `a2kit.AppBuilder(...).build()` → `a2kit.App(...)`. The `app` testing
  fixture (renamed `builder` by the prior change) is renamed back to
  `app` and yields a fresh `a2kit.App`. `install_connections` is
  retyped to `App`.
- ADR 0016 is superseded by a new ADR recording the narrowed contract.

## Capabilities

### New Capabilities

<!-- none — this change reshapes an existing capability -->

### Modified Capabilities

- `app-builder-runtime`: the builder/runtime split is no longer a
  consumer-visible distinction. Composition happens on a mutable
  `App`; the sealed runtime is internal; finishers seal; there is no
  public `build()`.
- `core-composition`: the three named composition verbs are exposed by
  `a2kit.App` (not `a2kit.AppBuilder`).

## Impact

- **Surface**: `a2kit.AppBuilder` and the public `build()` are removed
  from `a2kit.__all__` / `_LAZY_ATTRS`. `a2kit.App` is the single
  composition type. The sealed runtime is no longer a public name.
- **Entry points**: `a2kit.run`, `a2kit.packages.mcp.build_mcp_server`,
  `a2kit.testing.client` accept an `App` and seal it internally.
- **Blast radius**: every composition site — all examples, the test
  suite, downstream consumers — migrates `AppBuilder(...).build()` →
  `App(...)`. This re-touches the sites `split-app-builder-runtime`
  just migrated; accepted as the cost of landing on a contract there
  is no reason to move again.
- **Decision log**: supersedes ADR 0016; a new ADR is recorded.
- **Docs**: README, AGENTS.md, CHANGELOG, `docs/patterns/test-overrides.md`.
