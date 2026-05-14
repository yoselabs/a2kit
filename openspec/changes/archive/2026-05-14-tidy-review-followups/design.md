## Context

Two trivial-scope follow-ups bundled. The spec-validator fix is
pure prose; the validator's pattern-match expects SHALL/MUST on the
first non-blank line of a requirement body, and three pre-existing
requirements happen to wrap that first SHALL across a line break
(or use MAY ahead of SHALL). The `_verbs.py` split mirrors the
existing pattern of pulling pure-introspection helpers into a private
sibling (`_lifecycle_helpers.py`, `_list_helpers.py`,
`packages/di/_introspection.py`).

## Goals / Non-Goals

**Goals:**
- `openspec validate module-layout-discipline --strict` passes.
- `openspec validate type-correctness-gate --strict` passes.
- `openspec archive <next-change> --yes` succeeds without
  `--no-validate` (test by running validate after the rephrase).
- `src/a2kit/_verbs.py` drops to under 400 SLOC, opening headroom
  for the next verb feature.
- `tool.py` + `_verbs.py` + `_verb_validators.py` keep their existing
  public/private separation; consumer imports unchanged.

**Non-Goals:**
- Substantive spec edits. Only first-line modal verb placement moves;
  scenario lists are untouched.
- Changing what the validators do or how `_stamp` calls them.
- Adding mirror tests beyond what the ALLOW_LIST rationale documents.

## Decisions

### 1. Spec rephrases: keep titles, change body first line only

Renaming requirement titles risks future archive-tool drift (per the
CLAUDE.md warning about multi-wave dependencies). So the rephrase
strategy is: title stays verbatim; the first sentence of the body is
rewritten so SHALL/MUST appears on the FIRST non-blank line.

Examples:

| Before | After |
|---|---|
| `The total count of Python source files at the top level of \`src/a2kit/\` (\`src/a2kit/*.py\`, excluding \`__init__.py\` and \`__main__.py\`, and excluding the \`packages/\` subtree) SHALL be at most 12.` | `Core source SHALL contain at most 12 Python files at the top level of \`src/a2kit/\` (excluding \`__init__.py\`, \`__main__.py\`, and the \`packages/\` subtree).` |
| `The shared \`_APP_CTX: ContextVar\` used by \`build_full_cli\` and \`serve_command\` to propagate the active \`App\` across lazy subcommand dispatches SHALL be defined in \`a2kit.packages.cli.app_ctx\`.` | `\`_APP_CTX: ContextVar\` SHALL be defined in \`a2kit.packages.cli.app_ctx\` — used by \`build_full_cli\` and \`serve_command\` to propagate the active \`App\` across lazy subcommand dispatches.` |
| `In source files under \`src/a2kit/\`, ty diagnostics MAY be suppressed with inline \`# ty: ignore[<rule-code>]\` comments.` | `ty diagnostics in \`src/a2kit/\` SHALL only be suppressed via inline \`# ty: ignore[<rule-code>]\` comments.` |

### 2. `_verb_validators.py` extraction scope

What moves out of `_verbs.py`:
- `_PRIMITIVE_RETURN_TYPES` constant
- `_RESERVED_TOOL_NAME_PREFIX`, `_BUILTIN_RESERVED_TOOL_NAMES` constants
- `_check_return`, `_check_return_scope`, `_check_reserved_name`
- `_resolve_return_annotation`, `_walk_return_classes`
- `_WARN_ONCE_RESOLVE_RETURN`

What stays in `_verbs.py`:
- `_stamp`, `_compute_report_schema`, `_WARN_ONCE_REPORT_SCHEMA`
- `_kwargs_for`, `_reject_read_shaped_kwargs`,
  `_reject_annotations_flag_conflict`, `_build_annotation_kwargs`
- `_parse_timeout`
- Public decorators: `read`, `write`, `list_`, `_read_internal`

`_verbs.py` imports the validators from `_verb_validators.py` at
module top.

External consumers of internals are:
- `tests/test_decoration_warn_once.py` reads
  `tool_module._WARN_ONCE_RESOLVE_RETURN` and
  `tool_module._resolve_return_annotation` (where `tool_module` is
  the `a2kit._verbs` alias). After extraction, the test should
  import from `a2kit._verb_validators` directly OR continue accessing
  through `_verbs` if we re-export. Decision: re-export from `_verbs`
  to minimize test edits.
- `src/a2kit/packages/mcp/server.py` imports
  `_BUILTIN_RESERVED_TOOL_NAMES` and `_RESERVED_TOOL_NAME_PREFIX`
  from `a2kit._verbs`. After extraction, update server.py to import
  from `a2kit._verb_validators`.

### 3. Mirror-rule ALLOW_LIST

Add `src/a2kit/_verb_validators.py` to the ALLOW_LIST with rationale
("Pure introspection helpers for the verb decorators, extracted to
keep `_verbs.py` under the A2K014 SLOC budget. Covered indirectly
through every verb-decorated tool's stamp call.")

## Risks / Trade-offs

- **Risk:** Validator's "SHALL on first body line" assumption may be
  wrong; the pattern could match a different position. **Mitigation:**
  Verify after the rephrase by running `openspec validate <name> --strict`.
- **Risk:** Extracting `_resolve_return_annotation` breaks
  `_check_return_scope` if the inner caller can't find it. **Mitigation:**
  Both live in the same new file; cycle-free.
- **Risk:** `tests/test_decoration_warn_once.py` exercises
  `tool_module._resolve_return_annotation` via the
  `from a2kit import _verbs as tool_module` alias. After extraction
  the symbol is re-exported from `_verbs`, so the test keeps working
  unchanged.

## Migration Plan

Single commit on `main`:

1. Rephrase three requirement bodies in canonical specs.
2. Extract `_verb_validators.py` and re-export from `_verbs.py`.
3. Update `mcp/server.py` import path.
4. Add `_verb_validators.py` to mirror ALLOW_LIST.
5. Run `make lint`, `make test`, and `openspec validate` on the two
   touched specs.
