# Design — ruff-compatible-lint-codes

## Problem recap

a2kit emits lint codes in three shapes that all fail to coexist with
ruff's `# noqa` grammar:

| family | examples | source | ruff problem |
|---|---|---|---|
| dashed AST | `A2K-LAYER`, `A2K-IMPORT-DISCIPLINE`, `A2K-METADATA-PRIVATE` | `static.py` | hyphen is not a valid ruff code char; breaks the parser on a shared line |
| dashed raises | `A2K-RAISES-CLOSURE`, `A2K-RAISES-UNCOVERED`, `A2K-RAISES-NOT-TYPED` | `raises-closure-lint` (a2effect) | same hyphen problem |
| dashed rego | `REGO-NAME-COLLISION`, `REGO-BODY-DUP`, `REGO-GHA-PIN-SHA`, … | `_bundle/policies/*.rego` | same hyphen problem |
| numeric | `A2K002`, `A2K014`, `A2KR001` | `static.py`, `runtime.py` | shape is fine but `A2K`/`A2KR` is an unreserved namespace that visually collides with real ruff plugins |

ruff's noqa code grammar is, in effect, `[A-Z]+[0-9]+`: a run of capital
letters then a run of digits. ruff splits a `# noqa:` payload on commas
and parses each token under that grammar. A hyphenated token therefore
either is dropped (ignored) or, on a mixed line, corrupts the parse so
ruff and a2kit disagree about what the line suppresses.

## Chosen code shape

**`<PREFIX><NNN>` — a short alpha prefix then a zero-padded number,
matching `[A-Z]+[0-9]+` exactly.** Three reserved prefixes, one per rule
family:

| family | new prefix | example rename |
|---|---|---|
| static AST rules | `AK` | `A2K014` → `AK014`, `A2K-LAYER` → `AK200`, `A2K-METADATA-PRIVATE` → `AK210` |
| runtime checks | `AKR` | `A2KR001` → `AKR001` |
| Rego-policy rules | `RG` | `REGO-NAME-COLLISION` → `RG002`, `REGO-BODY-DUP` → `RG001`, `REGO-GHA-PIN-SHA` → `RG010` |

Rules:

- **Numeric codes keep their number, swap the prefix** (`A2K014` →
  `AK014`, `A2KR001` → `AKR001`) so the mechanical change is minimal and
  the number stays a stable mnemonic.
- **Dashed codes are assigned a stable number in a reserved band** so
  they never collide with the numeric codes that already exist. The
  dashed-AST codes take the `AK2xx` band (numeric ones occupy `AK0xx`);
  rego codes are numbered `RG0xx` (per-file) / `RG1xx` (GHA) blocks.
- **`AK` / `AKR` / `RG` are reserved by a2kit** as vendor prefixes (the
  README + the new capability document them) and are chosen to not
  collide with any current ruff built-in or popular plugin selector.

Why not keep `A2K###`: the digits are fine, but `A2K` reads as a normal
ruff plugin code and gives no signal that a *different* tool owns it; a
distinct short prefix (`AK`) makes the ownership unambiguous on a shared
line while staying inside ruff's grammar.

Why not register a2kit codes *into* ruff (entry-point plugin): ruff's
plugin model is Rust-side and not an open extension point for
third-party Python rules; co-suppression does not need ruff to *know*
a2kit's rules — it only needs the two tools to parse the same line
without one corrupting the other. Grammar compatibility achieves that;
plugin registration is unnecessary scope.

## Suppression grammar

One grammar, a strict superset of ruff's:

```
# noqa[: <CODE>[, <CODE>]*] [ -- <reason text>]
   where <CODE> matches [A-Z]+[0-9]+   (ruff-shaped)
```

- **Bare `# noqa`** = wildcard (suppress every a2kit rule on the line),
  unchanged from today — but discouraged (it also tells ruff to wildcard).
- **`# noqa: AK014, S603`** — a2kit's `parse_noqa` collects `{AK014,
  S603}`, matches its own rule against `AK014`, and lets `S603` fall
  through harmlessly; ruff collects the same set, honors `S603`, and
  ignores `AK014` as an unknown code. Neither parser breaks because both
  tokens are `[A-Z]+[0-9]+`.
- **` -- <reason>` suffix** is preserved verbatim from the existing
  convention (commit `83819db`): the literal separator is ` -- `
  (space-dash-dash-space). It stays **mandatory for `RG*`** rules (the
  former `REGO-*` hard-error rule) and conventional for `AK*`/`AKR*`.
- **`parse_noqa` ownership filter.** `parse_noqa` already returns the
  full code set per line; `suppressed(rule)` only matches against
  a2kit-owned codes, so foreign (ruff) codes on the line are inert for
  a2kit. No new logic is needed beyond accepting the new prefixes — the
  existing comma/`--` parser is grammar-agnostic.

## Legacy alias table

A frozen mapping `LEGACY_CODE_ALIASES: dict[str, str]` (old → new) ships
so that:

- a consumer's existing `# noqa: A2K-LAYER` and lint-config
  `disabled = ["A2K014"]` keep resolving during a deprecation window —
  `parse_noqa` / the disable-list reader normalize a recognized legacy
  code to its new code before matching.
- the alias resolution is **one-directional and lossless**: every legacy
  code maps to exactly one new code; the table is the single source of
  truth and is asserted complete (every current code has an entry).

The window is a deprecation, not a permanent dual-namespace: emitted
findings always use the new code; only *input* (suppressions, config)
accepts the legacy spelling. A follow-up may remove the table.

## Migration plan

This is the load-bearing, high-blast-radius part. Three mechanical
sweeps, each with a guard against silent loss:

1. **Code constants + parser (engine).** Rename the constants in
   `static.py` / `runtime.py`, the `REGO_RULE_PREFIX` handling in
   `_bundle/extract_facts.py`, and the rule-ID literals in
   `_bundle/policies/*.rego`. Add `LEGACY_CODE_ALIASES` and wire it into
   `parse_noqa` + the disable-list reader. (Engine code — authored in the
   implementation step, not here.)
2. **Bulk-rewrite existing suppressions.** A scripted `s/<old>/<new>/`
   over every `# noqa:` site in `src/` and `tests/`, driven by the alias
   table so the rename is exhaustive and 1:1. **No-silent-truncation
   guarantee:** the rewrite asserts (a) the count of `# noqa:` lines is
   unchanged before/after, (b) every rewritten code is a key in the alias
   table (an unrecognized code aborts the sweep rather than being
   dropped), and (c) the ` -- <reason>` suffix on each line is preserved
   byte-for-byte. A diff review confirms no suppression vanished.
3. **Regenerate snapshots/fixtures.** The lint snapshot fixtures embed
   code strings; regenerate them against the new codes. The regeneration
   is gated by a test that asserts the *set of rules represented* in the
   snapshots is identical before/after the rename (only the spelling
   changed) — so a regenerate cannot silently drop a rule's coverage.

## Why this is isolated from the surface waves

- **No shared code.** The surface waves touch `app`, `routers`,
  surfaces, `http/build.py`, MCP/CLI binding. This change touches only
  the lint package, the noqa sites, and snapshots. There is zero file
  overlap, so it neither blocks nor is blocked by Waves 0–3.
- **Different blast-radius profile.** The surface waves are a *semantic*
  break (tool names change); this is a *lexical* rename of diagnostic
  strings. Co-landing would conflate two unrelated review surfaces and
  inflate the surface-wave diffs with hundreds of noqa edits.
- **ADR 0028 §7 sequences it ORTHOGONAL** explicitly ("own track, big
  mechanical blast radius — do isolated"). The only soft coupling is that
  the dup-name lint rule (decision 6, `validate-composition`) wants "a
  ruff-compatible code"; that rule simply *inherits* the shape this
  change defines and does not need to co-land.

## Alternatives considered

- **Keep `A2K###`, only fix the dashed codes.** Rejected: leaves the
  unreserved-namespace ambiguity and means two code shapes (`A2K###` +
  the renamed dashed ones) instead of one uniform family.
- **Map dashed codes to ruff-style by hashing the name to a number.**
  Rejected: unstable / unreadable; a curated number table is greppable
  and stable.
- **Hard cutover, no alias table.** Rejected: every consumer's existing
  suppressions would break in one release; the alias window makes the
  rename adoptable.
