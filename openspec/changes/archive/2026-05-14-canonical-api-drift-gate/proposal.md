# Canonical-API drift gate — extend symbol-drift to method names

## Why

v0.33 shipped `tests/test_readme_symbol_drift.py` — parses
`README.md`, asserts every claimed public symbol resolves on the
live module surface. It caught ten stale references in its first
pass. But it only covers **module-level symbols** (`a2kit.X`,
`from a2kit import Y`). Method names on documented types slip past
silently.

Concrete failure: round-9 feedback flagged
`TestClient.call` → `.invoke` rename. The README probably accesses
the test client via the lazy `a2kit.testing` accessor without
spelling out `.call` specifically, so the README-drift gate didn't
notice. Every consumer's test suite broke on bump.

The consumer's ask (round 9, ask 3) is direct:

> Extend the symbol-drift gate to per-class method surface for at
> least these canonical types: `TestClient`, `App`, `Router`,
> `ToolContext`, the verb decorators. Walk every method name
> claimed in the README's code blocks (not just `a2kit.X`
> references) and assert it exists.

That's the right shape. The drift gate's failure mode is bounded:
it catches consumer-interface stability at CI time, which is exactly
where the v0.33 release cadence (6 releases in 2 days) needs
defense.

## What Changes

- **EXTEND** `tests/test_readme_symbol_drift.py` to parse method
  references in README code blocks. Approach:
  1. Walk all fenced code blocks in `README.md` (and possibly
     `OPERATIONAL_CONTRACTS.md` and `examples/*/README.md` if the
     scope is expanded).
  2. For each block, extract `<obj>.<method>(` patterns where
     `<obj>` resolves to a documented canonical type.
  3. Assert `hasattr(<obj>_type>, "<method>")` on the live module.
  4. Fail loudly on mismatch with a hint pointing at where in the
     README the call is documented.

- **DEFINE** the canonical-type allowlist explicitly in the test:
  `TestClient`, `App`, `Router`, `ToolContext`, and the verb
  decorators `read`, `write`, `list_`. Anything outside this set
  is best-effort.

- **ADD** a sister test `tests/test_canonical_apis.py` that exercises
  the documented call shapes end-to-end with a tiny fixture app —
  the consumer's alternate ask (round 9, ask 3, option 2). The
  two tests are complementary: parsing catches REFERENCE drift;
  the script catches BEHAVIORAL drift (the method exists but
  returns a different shape).

- **DOCUMENT** in `docs-code-parity` spec the extended drift-gate
  contract.

## Impact

- One new fail-loud test in CI (or one extended existing test).
- Catches renames like `.call` → `.invoke` at PR time, not at
  consumer-bump time.
- No code-behavior changes; tooling only.

## Risk

Low. The parser needs reasonable heuristics for "what's a canonical
type reference" — start strict (explicit allowlist) and expand if
real false-positives appear. False-negatives (drift that slips past)
are the bug we already have; no regression possible.

The bigger design question: where does the README/canonical-API
parity boundary sit?

```
                  parses for symbols            asserts behavior
                  ↓                              ↓
   README        ──→ test_readme_symbol_drift ──→ exists check
                  ↓
   doc blocks    ──→ THIS CHANGE          ──→ exists check on
                                              method names
                  ↓
   call shape    ──→ test_canonical_apis  ──→ end-to-end behaves
   examples
```

The current gate covers tier 1. This change adds tier 2 (parsing
method names) and tier 3 (running them). All three together close
the silent-rename gap.
