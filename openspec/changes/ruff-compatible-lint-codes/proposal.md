## Why

Friction #7 from a2kay (ADR 0028, surface-feedback round): a2kit's lint
rule codes do not fit ruff's `# noqa` grammar, so a2kit codes and ruff
codes **cannot be co-suppressed on the same line**.

Two collision classes exist today:

- **Dashed codes** — `A2K-IMPORT-DISCIPLINE`, `A2K-LAYER`,
  `A2K-RAISES-CLOSURE`, `A2K-METADATA-PRIVATE`, `REGO-NAME-COLLISION`,
  `REGO-GHA-PIN-SHA`, … (`packages/lint/static.py`,
  `packages/lint/_bundle/policies/*.rego`). ruff's noqa code grammar is
  `[A-Z]+[0-9]+` (a letter-run then a digit-run); a hyphenated token is
  not a valid ruff code, so ruff silently ignores it, and worse, a mixed
  line like `# noqa: S603, A2K-LAYER` is parsed by ruff as the single
  malformed code `A2K-LAYER` after the comma split — ruff cannot honor
  the `S603` half cleanly and a2kit/ruff disagree about what the line
  suppresses.
- **`A2K###` / `A2KR###` numeric codes** — `A2K002`, `A2K014`,
  `A2KR001`, … These are shaped like ruff codes but reuse a vendor
  namespace (`A2K`/`A2KR`) that is not reserved and overlaps the visual
  space of real ruff plugins, making a shared noqa line ambiguous about
  *which* tool owns the code.

Net effect: a consumer who must suppress a ruff finding **and** an a2kit
finding on one line has no grammar that both tools agree on, and the
hyphenated codes break ruff's parser outright. The dup-name lint rule
that ADR 0028 decision 6 adds is also specified to carry "a
ruff-compatible code" — it cannot until the code shape is fixed.

## What Changes

Rename a2kit's lint rule codes to a **ruff-`noqa`-grammar-safe shape**
(`[A-Z]+[0-9]+`) under a distinct, reserved vendor prefix, and define
one **inline-suppression grammar** that is a strict superset of ruff's
`# noqa: <CODE>[, <CODE>]*` so a2kit codes and ruff codes can be listed
together on the same line and each tool honors its own.

- **Code shape.** Every a2kit lint code becomes `<PREFIX><NNN>` where
  `<PREFIX>` is a short alpha run and `<NNN>` is a zero-padded number.
  Three families map to three reserved prefixes: static AST rules →
  `AK`, runtime checks → `AKR`, Rego-policy rules → `RG`. Dashed codes
  are assigned stable numbers (e.g. `A2K-LAYER` → `AK200`,
  `REGO-NAME-COLLISION` → `RG002`); existing numeric codes are
  re-stamped onto the new prefix (`A2K014` → `AK014`, `A2KR001` →
  `AKR001`). A frozen **legacy→new alias table** ships so old codes in
  consumer config / suppressions resolve during a deprecation window.
- **Inline-suppress grammar.** `# noqa: <CODE>[, <CODE>]* [ -- <reason>]`
  where each `<CODE>` is ruff-grammar-shaped. a2kit's `parse_noqa`
  ignores codes it does not own (ruff codes pass through untouched), and
  ruff ignores a2kit's `AK*`/`AKR*`/`RG*` codes as unknown — but neither
  tool's parser *breaks* on the other's codes, because all codes are now
  the same `[A-Z]+[0-9]+` shape. The ` -- <reason>` suffix convention is
  preserved (still mandatory for `RG*` rules, conventional for the rest).
- **Bulk migration.** Every existing `# noqa: A2K…` / `# noqa: REGO-…`
  suppression in the tree is rewritten to the new code, and the lint
  snapshot fixtures are regenerated against the new codes — with a
  **no-silent-truncation** guarantee (the migration is a 1:1 rename, no
  suppression is dropped, every rewritten line is diff-reviewed).

## Capabilities

### Added Capabilities

- `lint-code-format` — the cross-cutting contract for a2kit's lint code
  *shape* (`[A-Z]+[0-9]+`, reserved vendor prefixes) and the inline
  `# noqa` suppression grammar (ruff-superset, co-suppression-safe,
  legacy-alias resolution). This contract was previously implicit /
  unowned; it is now a named capability so every lint capability inherits
  one code-shape rule.

### Modified Capabilities

- `rego-policy-layer` — the `noqa -- reason` suppression requirement is
  restated against ruff-safe `RG*` codes (was `REGO-*`); the dashed
  `REGO-…` rule IDs are renamed, the mandatory- ` -- reason` rule for
  `RG*` is preserved.
- `module-layout-discipline` — the `A2K-METADATA-PRIVATE` rule and the
  `A2K014` SLOC-budget noqa-freedom requirements are restated against
  `AK*` codes (`A2K-METADATA-PRIVATE` → `AK210`, `A2K014` → `AK014`).
- `raises-closure-lint` — the three `A2K-RAISES-*` rule IDs and their
  entry-point names are restated against ruff-safe `AK*` codes.

## Impact

- **Large mechanical blast radius, sequenced isolated.** Every existing
  `# noqa: A2K…` / `# noqa: REGO-…` comment in `src/` and `tests/` is
  rewritten, and every lint snapshot / fixture that embeds a code string
  is regenerated. This touches many files for a flat rename, so it rides
  its own ORTHOGONAL track (ADR 0028 §7), independent of surface Waves
  0–3 — it shares no code with the surface model and can land any time.
- Affected code (out of scope to author here, listed for impact):
  `src/a2kit/packages/lint/static.py` (code constants + `parse_noqa`),
  `runtime.py` (`A2KR*`), `_bundle/extract_facts.py` (noqa grammar +
  `REGO_RULE_PREFIX`), `_bundle/policies/*.rego` (rule-ID literals),
  every `# noqa:` site, the lint snapshot fixtures, and
  `pyproject.toml [tool.a2kit.lint]` disable lists + the
  `[project.entry-points."a2lint.rules"]` keys.
- Consumers: a one-time `s/A2K-…/AK…/`, `s/REGO-…/RG…/`,
  `s/A2K0/AK0/`, `s/A2KR/AKR/` in their own suppressions and lint
  config; the legacy-alias table keeps old codes resolving through a
  deprecation window so the rename is not a hard cutover.

## Non-goals

- **Not** new lint rules or changed rule *semantics* — only the code
  *string* and the suppression *grammar* change; every rule fires on
  exactly the same conditions as before.
- **Not** the dup-name lint rule itself (ADR 0028 decision 6 /
  `validate-composition`) — that rule lands on its own track and merely
  *inherits* the ruff-safe code shape this change establishes.
- **Not** any surface-layer change (Waves 0–3); this is deliberately
  decoupled from the `surfaces` model.
- **Not** adopting ruff's plugin/entry-point system to register a2kit
  codes *into* ruff — co-suppression is achieved by grammar compatibility,
  not by teaching ruff a2kit's rules.
