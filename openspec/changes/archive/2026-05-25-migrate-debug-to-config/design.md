## Context

`a2kit-config-surface` shipped the engine but deferred the canonical
worked example (`App.debug` → `config.debug`) to keep the change
tight. This is the follow-up. ADR 0022 (provider-chain config model)
is the load-bearing rationale: the consumer-owned debug concern must
escape the source code.

## Goals / Non-Goals

**Goals:**
- Remove the `debug` kwarg from `App.__init__`.
- Add `debug: bool = False` to `A2kitConfig` (top-level field).
- Preserve `app.debug` attribute access (so callers reading it keep working).
- Ship the deferred README + AGENTS.md docs that explain the config story
  end-to-end with both knobs (`A2KIT_DEBUG` and `A2KIT_MCP__STRUCTURED_OUTPUT`).
- Update operational-contracts spec text to use new construction form.

**Non-Goals:**
- Consumer repo migrations (a2web, a2atlassian, a2db, a2skill, a2sdlc).
  Each ships its own PR per-repo.
- Adding a `CliConfig.json` knob for tool invocation. That's a separate
  follow-up (`cli-json-flag`).
- A general "deprecate-with-warning" period. Per AGENTS.md no-backwards-
  compat principle, the kwarg goes away in one step.

## Decisions

### D1. Remove the kwarg; preserve the attribute

The breaking surface is the kwarg. `App.debug` (the attribute) is
preserved by reading `self.config.debug` at construction and assigning
to `self.debug`. Two reasons:

1. Internal code (`runtime.py:275 — debug=app.debug`) already reads
   the attribute. Keeping it cheap saves a migration.
2. External callers may inspect `app.debug` for diagnostics; the
   attribute is the read API, the kwarg was the write API. Only the
   write API was anti-pattern.

### D2. TypeError with migration hint on kwarg use

Match the existing `_raise_unexpected_kwargs` pattern in `app.py`.
Hint: "Use `A2kitConfig(debug=True)` or env `A2KIT_DEBUG=true`."

### D3. `config.debug` lives at the top level, not under a sub-model

It is cross-cutting (affects MCP wire, HTTP, CLI). Sub-models are for
subsystem-scoped concerns. Same shape as the existing
`A2kitConfig.debug` placeholder we already had in mind.

### D4. Bundle docs with the migration

The README "Configuration" section and AGENTS.md paragraph were
deferred from `a2kit-config-surface` to keep that change focused.
Landing them here is correct timing: with `A2KIT_DEBUG` joining
`A2KIT_MCP__STRUCTURED_OUTPUT`, the docs have two concrete examples
to anchor the precedence and convention explanations.

### D5. Update operational-contracts spec text — behavior unchanged

The spec's scenarios cite `App(debug=True)` in setup; the actual
contract (envelope `traceback` field, CLI stderr traceback) is
about the resulting *state*, not the construction syntax. Reword the
scenarios to use `A2kitConfig(debug=True)` (clearer for spec readers
since env-via-monkeypatch noise dominates a scenario otherwise).

## Risks / Trade-offs

- **Risk**: External consumer code in untracked repos breaks at runtime.
  **Mitigation**: TypeError carries the migration hint; mechanical fix.
  No silent breakage — the kwarg is structurally rejected.

- **Risk**: Test sites that used `App(debug=True)` to test the *debug
  state* now need monkeypatch-based env or explicit config kwarg.
  **Mitigation**: `A2kitConfig(debug=True)` keeps tests deterministic
  without env pollution. The autouse `_clear_a2kit_env` fixture pattern
  from `tests/config/conftest.py` lands more broadly if needed.

- **Risk**: README section bloats with both knobs documented.
  **Mitigation**: One precedence diagram, two short examples, link
  to ADR 0022 for the full story. Keep it tight.

## Migration Plan

1. Add `debug: bool = False` to `A2kitConfig`.
2. Update `App.__init__`: remove the `debug` kwarg, source the attribute
   from `self.config.debug` instead.
3. Add migration-hint branch to `_raise_unexpected_kwargs`.
4. Audit and rewrite the ~6 test sites passing `App(debug=True)`.
5. Update operational-contracts spec, ADRs 0017/0019 surface tables,
   README "Configuration" section, AGENTS.md "Patterns" paragraph,
   ANTIPATTERNS.md entry, OPERATIONAL_CONTRACTS.md citations,
   CHANGELOG.md.
6. Verify full suite + ruff + type check + mirror lint.

## Open Questions

None.
