## Context

Round-5 and round-6 cleanups shipped four new affordances and tightened
one operational contract. The corresponding doc and spec surfaces drifted
out of step:

- README still describes round-3 testing ergonomics.
- `tool-description-contract` spec mandates `A2KitMeta.param_descriptions`;
  code mutates `fn.__annotations__` and never touches meta.
- `OPERATIONAL_CONTRACTS.md` Q8 + `operational-contracts` spec say all
  factories raise `AmbientContextMissing`; lazy singleton factories
  instantiated during dispatch demonstrably work.
- `di-container-package` spec lists two attributes for snapshot/restore;
  the shipped override path mutates three.

This change is doc-and-spec only. No production code edits. It pairs
with a sibling change `cleanup-round-5-6-code-shape` that takes code-shape
items; both changes share three modified specs but partition the
requirements between them.

## Goals / Non-Goals

**Goals**

- Bring `README.md` and `OPERATIONAL_CONTRACTS.md` into line with shipped
  round-5/6 behaviour.
- Resolve the three spec/code divergences in a way that preserves shipped
  behaviour and codifies it.
- Avoid a structural collision with the sibling code-shape change.

**Non-Goals**

- No production code (`src/`) edits.
- No new tests, no new fixtures.
- No tightening of the LDD contract beyond clarifying "active dispatch
  reachable" — the lazy-factory case is the only edit.
- No deeper rework of override APIs (the sibling change owns that).

## Decisions

### [J] `param_descriptions` storage — option (a): meta AND annotations

**Pick:** Resolved descriptions SHALL be stored on
`A2KitMeta.param_descriptions: Mapping[str, str]` AND continue to be
mirrored on `fn.__annotations__` (the current implementation path).

**Why option (a)** over the alternatives:

- (b) "meta-only, drop annotation mutation, add custom MCP schema
  post-pass" — costs us a custom schema-gen path on the FastMCP side,
  more code, more failure modes, more drift risk. Rejected.
- (c) "amend the spec to allow annotation mutation, no meta field" —
  cheapest, but leaves middleware and tooling without a documented place
  to read the descriptions. Anyone wanting them has to re-parse the
  function signature. Spec already says "no docstring parsing happens
  per request" — option (c) honours the letter but not the spirit.
  Rejected.
- (a) — costs ~10 LOC on the `tool.py` augmentation path: build the dict
  while we're already iterating, attach it to `A2KitMeta`. Annotation
  mutation stays for FastMCP schema gen. Meta is authoritative for any
  downstream reader.

**Spec edit:** the requirement is reworded to mandate both surfaces
(meta as canonical, annotations as the schema-gen carrier) and a new
scenario asserts `meta.param_descriptions` is populated and matches.

### [K] LDD Q8 — "active dispatch reachable", not "tool body only"

The shipped LDD ContextVar is set by the dispatcher BEFORE the tool body
runs and torn down AFTER. Any code path reached during that window sees
the ctx. That includes:

- the tool body itself,
- any helper functions / coroutines it calls,
- async tasks spawned via `asyncio.gather`, `create_task`, `TaskGroup`
  (Python's contextvars copy-on-task semantics),
- **lazy singleton factories** invoked the first time the tool resolves
  the dependency during dispatch.

What's still illegal: `on_startup`, `on_shutdown`, module-import-time
code, anything before/after the dispatcher's ctx window.

**Spec edit:** rephrase the requirement to "active dispatch reachable"
and rephrase the lifecycle scenario to make it about the
*pre-dispatch context*, not the abstract concept of a "factory". The
Q8 prose in `OPERATIONAL_CONTRACTS.md` gets the same rewording as a
task.

### [N] `di-container-package` — three attributes, not two

The shipped snapshot/restore path captures `_providers`, `_singletons`,
AND `_async_factories`. Without the third, restoring a snapshot taken
after an async-singleton override would leave a stale async-factory
entry that raises "async factory" on sync resolve.

**Spec edit:** the requirement reads "three attributes" instead of "two
dicts". The two scenarios that mention `_providers` and `_singletons`
get `_async_factories` added in matching positions. No new requirement;
just expanding the attribute list in the existing one.

### Coordination with sibling `cleanup-round-5-6-code-shape`

The sibling change is expected to introduce `Container._override(...)`
as a single method that subsumes snapshot/restore. If the sibling lands
first, this change's `di-container-package` MODIFIED block needs to be
reworded at apply time to describe `_override` instead of
`_snapshot`/`_restore`. If this change lands first, the sibling reshuffle
satisfies the three-attribute contract trivially.

Either ordering works. Apply-time check: re-read both deltas before
each `openspec validate --strict` and merge if both touch the same
requirement.

## Risks / Trade-offs

- **[Risk] Sibling change touches same specs** → Mitigation: deltas in
  this change name a single MODIFIED requirement per spec. The sibling
  is expected to add NEW requirements (or modify disjoint ones).
  `openspec validate --strict` catches any duplicate-requirement collision.
- **[Risk] README rewrite over-promises** → Mitigation: every new
  affordance in the testing section has a working test under `tests/`
  already. Cross-reference the test file in the README example so the
  example stays grep-able.
- **[Risk] Q8 rewording loosens contract** → Mitigation: the new
  wording explicitly enumerates the illegal call sites (startup,
  shutdown, module-init). Lazy factories are the only addition. The
  scenario asserting `on_startup` raises is unchanged.

## Migration Plan

Pure doc/spec change. No rollout. No rollback. Archive after the README
and OPERATIONAL_CONTRACTS edits land.
