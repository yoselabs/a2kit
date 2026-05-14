## Why

The code review on `tidy-v035-deferred-items` flagged two minor
follow-ups the wave punted. Closing them now keeps the canonical spec
clean for future archives and rebuilds `_verbs.py`'s SLOC budget
headroom before the next verb-feature change trips A2K014.

Out of scope:
- Process feedback on BDD-first commit ordering (no code change;
  applies to future waves only).

## What Changes

- Inject SHALL/MUST into the FIRST body line of three canonical spec
  requirements that fail strict validation. The substantive content
  is unchanged; only the modal-verb placement moves. Affected
  requirements:
  - `module-layout-discipline`: "Core source tree is at most 12 files"
  - `module-layout-discipline`: "`_APP_CTX` lives in `packages/cli/app_ctx`"
  - `type-correctness-gate`: "ty diagnostics suppressed only via inline `# ty: ignore[code]`"
- Extract the return-annotation validators (`_check_return`,
  `_resolve_return_annotation`, `_walk_return_classes`,
  `_check_return_scope`, `_check_reserved_name`, plus the constants
  they need) from `src/a2kit/_verbs.py` into a new private
  `src/a2kit/_verb_validators.py`. `_verbs.py` keeps the
  verb decorators + `_stamp` + annotation builders. Net effect:
  `_verbs.py` shrinks from ~522 SLOC to under 400, giving 100+ SLOC
  headroom under the A2K014 budget.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `module-layout-discipline`: rephrase two requirement bodies so
  SHALL/MUST appears on the first line (strict-validator gate); add
  scoping rule for the new `_verb_validators.py` sibling.
- `type-correctness-gate`: rephrase one requirement body so SHALL
  appears on the first line.

## Impact

- `openspec/specs/module-layout-discipline/spec.md` → 2 requirement
  bodies rephrased; `_verb_validators.py` added to ALLOW_LIST
  rationale (handled in `src/a2kit/packages/lint/rules/mirror.py`).
- `openspec/specs/type-correctness-gate/spec.md` → 1 requirement
  body rephrased.
- `src/a2kit/_verb_validators.py` (NEW) → return-annotation validators
  and reserved-name guards.
- `src/a2kit/_verbs.py` → imports validators from
  `_verb_validators.py` instead of defining them locally.
- `src/a2kit/packages/lint/rules/mirror.py` → add
  `_verb_validators.py` to ALLOW_LIST with rationale.
- `src/a2kit/packages/mcp/server.py` → `_BUILTIN_RESERVED_TOOL_NAMES`
  and `_RESERVED_TOOL_NAME_PREFIX` import path updated.
- Strict `openspec archive` and `openspec validate <name> --strict`
  pass on `module-layout-discipline` and `type-correctness-gate`
  without `--no-validate`.
- No public-surface changes; no test changes besides any path-update
  required by the `_verb_validators.py` extraction.
