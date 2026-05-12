## Why

Round-5/6 cleanup shipped four new affordances (`TestClient.override`, async
singleton factories, Google-style docstring → param descriptions, `TestClient.call_wire`)
and tightened the LDD ambient-context contract. Three of those landed in code
without their doc/spec counterparts catching up:

- `README.md` still teaches the old `app.provide(T, fake)` override pattern
  and never mentions `TestClient.override`, async `app.singleton`,
  `call_wire`, or docstring-pulled param descriptions.
- `openspec/specs/tool-description-contract/spec.md` requires `param_descriptions`
  to be stored on `A2KitMeta`, but the implementation mutates
  `fn.__annotations__` instead. Same observable behaviour, divergent
  contract: middleware reading `meta.param_descriptions` finds nothing.
- `OPERATIONAL_CONTRACTS.md` Q8 (mirrored in
  `openspec/specs/operational-contracts/spec.md`) says singleton/provider
  factories raise `AmbientContextMissing`, but factories instantiated
  lazily *during dispatch* already have the ambient ctx and work fine.
  Doc/spec says "factories raise"; code says "factories work during dispatch".
- `openspec/specs/di-container-package/spec.md` describes test override as
  mutating `_providers` and `_singletons` only. The shipped override path
  also mutates `_async_factories` (otherwise sync-resolving an
  async-registered override raises a stale "async factory" error). The
  spec didn't anticipate the `singleton-async-factories` interaction.

Closing these gaps now keeps the contract surface honest and unblocks the
companion `cleanup-round-5-6-code-shape` change from inheriting drift.

## What Changes

Docs and specs only. No production code edits land in this change.

- Rewrite `README.md` testing section to teach `TestClient.override(T, fake)`
  as the recommended override path; keep `app.provide(T, fake)` as the
  underlying mechanism. Add a short example of `app.singleton(T, async_factory)`.
  Document `call_wire` next to `invoke`. Mention Google-style docstring
  `Args:` → MCP/CLI parameter descriptions. Reference `AmbientContextMissing`
  and the ambient LDD ctx contract.
- Amend `tool-description-contract` spec: `param_descriptions` SHALL be
  stored on `A2KitMeta` AND `fn.__annotations__` SHALL continue to carry
  the resolved descriptions (so FastMCP schema generation keeps working).
  Meta is authoritative for any reader/middleware that wants the descriptions
  without re-walking the annotation tree.
- Amend `operational-contracts` spec and edit `OPERATIONAL_CONTRACTS.md` Q8:
  LDD primitives require an active dispatch; they work in *any* code
  reachable from a tool dispatch (including async singleton factories
  instantiated lazily during dispatch). They do NOT work during startup,
  shutdown, module init, or any other pre-dispatch context.
- Amend `di-container-package` spec to acknowledge `_async_factories` as
  the third attribute touched by `_snapshot`/`_restore` (or by whatever
  `Container._override` method the sibling code-shape change introduces).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `tool-description-contract`: requirement "Per-parameter descriptions
  resolved from the docstring" tightened — resolved descriptions SHALL
  be stored on `A2KitMeta.param_descriptions` (annotation mutation
  remains permitted for FastMCP schema gen).
- `operational-contracts`: requirement "LDD primitives require an active
  tool dispatch" reworded — the rule is "active dispatch reachable",
  not "tool body only". Lazy singleton factories instantiated during
  dispatch ARE legal call sites; `on_startup`/`on_shutdown`/module-init
  remain illegal.
- `di-container-package`: requirement "Container exposes a sealed
  test-only snapshot/restore pair" tightened — snapshot/restore SHALL
  capture and replace `_providers`, `_singletons`, AND `_async_factories`.

## Impact

- `README.md` — testing section, migration notes, scattered examples.
- `OPERATIONAL_CONTRACTS.md` — Q8 wording.
- `openspec/specs/tool-description-contract/spec.md` — one MODIFIED
  requirement.
- `openspec/specs/operational-contracts/spec.md` — one MODIFIED requirement.
- `openspec/specs/di-container-package/spec.md` — one MODIFIED requirement.
- No production code (`src/`) edits. No test edits.

### Coordination with sibling change `cleanup-round-5-6-code-shape`

The sibling change touches code shape (likely introducing
`Container._override` and consolidating override mechanics). The
`di-container-package` MODIFIED requirement here is worded so that
either ordering works:

- If the sibling lands first and introduces `_override`, this change's
  MODIFIED block is consistent (still names the three attributes that
  `_override` mutates, just framed as the new method's contract).
- If this change lands first, the sibling's later code reshuffle
  satisfies the three-attribute contract trivially.

If both changes end up with MODIFIED blocks on the same requirement,
`openspec validate --strict` will catch the structural collision and
we resolve by merging into one delta at archive time.
