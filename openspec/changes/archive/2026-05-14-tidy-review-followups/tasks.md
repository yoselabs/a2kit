## 1. Spec rephrases (canonical specs validate strict)

- [x] 1.1 Rewrite the first body line of `### Requirement: Core source tree is at most 12 files` in `openspec/specs/module-layout-discipline/spec.md` so SHALL appears on the first non-blank line; preserve the existing scenario.
- [x] 1.2 Rewrite the first body line of `### Requirement: \`_APP_CTX\` lives in \`packages/cli/app_ctx\`` in the same file so SHALL appears on the first non-blank line; preserve both existing scenarios.
- [x] 1.3 Rewrite the first body line of `### Requirement: ty diagnostics suppressed only via inline \`# ty: ignore[code]\`` in `openspec/specs/type-correctness-gate/spec.md` so SHALL appears on the first non-blank line; preserve both existing scenarios.
- [x] 1.4 Confirm `openspec validate module-layout-discipline --strict` and `openspec validate type-correctness-gate --strict` both pass.

## 2. `_verb_validators.py` extraction

- [x] 2.1 Create `src/a2kit/_verb_validators.py` with `_PRIMITIVE_RETURN_TYPES`, `_RESERVED_TOOL_NAME_PREFIX`, `_BUILTIN_RESERVED_TOOL_NAMES`, `_WARN_ONCE_RESOLVE_RETURN`, `_check_return`, `_check_return_scope`, `_check_reserved_name`, `_resolve_return_annotation`, `_walk_return_classes` (verbatim move from `_verbs.py`).
- [x] 2.2 In `src/a2kit/_verbs.py`, replace those definitions with `from a2kit._verb_validators import ...`; re-export `_resolve_return_annotation` and `_WARN_ONCE_RESOLVE_RETURN` so existing test imports keep working.
- [x] 2.3 Update `src/a2kit/packages/mcp/server.py` import of `_BUILTIN_RESERVED_TOOL_NAMES` / `_RESERVED_TOOL_NAME_PREFIX` to read from `a2kit._verb_validators`.
- [x] 2.4 Add `src/a2kit/_verb_validators.py` to `ALLOW_LIST` in `src/a2kit/packages/lint/rules/mirror.py` with rationale.
- [x] 2.5 Verify `wc -l src/a2kit/_verbs.py` reports under 400 SLOC and `uv run a2kit lint static src/` emits no `A2K014` on `_verbs.py`.

## 3. Validation + archive

- [x] 3.1 Run `make lint` and `make test` end-to-end; both green.
- [x] 3.2 Run `openspec validate --changes tidy-review-followups --strict`; confirm green.
- [x] 3.3 Commit with `chore: address review followups — canonical-spec SHALL placement + _verbs.py headroom` and run `openspec archive tidy-review-followups` (this time WITHOUT `--no-validate`, to confirm the spec fixes actually closed the gate).
