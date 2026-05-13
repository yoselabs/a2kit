# Prune dead decorator surface

## Why

A consumption-interface audit (explore session 2026-05-13) measured
real usage of every public kwarg across all six example apps and the
in-repo test suite. Two surfaces have **zero live readers** and
inflate every author's IDE autocomplete with knobs nobody turns:

- **`tags=`** kwarg on `@a2kit.read/write/list_/tool`. Author-set tags
  never appear in any example, downstream consumer, or test fixture
  (only one test fixture sets it for coverage). The MCP server and
  OTEL middleware read `meta.tags`, but every tag they care about is
  framework-auto-stamped (`"read"`, `"write"`, `"list"`, `"_meta"`).
  No author has ever set the kwarg.
- **`Cap` enum + `capabilities` registry** in `a2kit.capabilities`.
  The grep is conclusive: appears in its own unit test, in one
  lint-rule "did you mean Cap.X?" suggestion string, and nowhere else.
  No decorator usage, no consumer reads, no runtime contract. Pure
  aspirational surface.

`App(..., debug=False)` was originally listed in this proposal as
dead. **It is not.** Re-verification found two live readers:
`src/a2kit/packages/cli/builder.py:349` (stderr traceback emission)
and `src/a2kit/packages/mcp/server.py:290`
(`fastmcp_kwargs["mask_error_details"]`). Three tests in
`test_operational_contracts.py` cover the behaviour. Out of scope
for this change.

Removing these shrinks the top-level surface (`a2kit.Cap`,
`a2kit.capabilities`) by two exports and the decorator surface by
one kwarg slot per verb (4 verbs × 1 = −4 slots). Zero behaviour
change for any real consumer.

## What changes

- **REMOVE** `tags` kwarg from `@a2kit.read`, `@a2kit.write`,
  `@a2kit.list_`, `@a2kit.tool`. Framework-derived tags
  (`"read"`/`"write"`/`"list"`) keep being stamped automatically.
- **REMOVE** `a2kit.Cap` and `a2kit.capabilities` from the
  top-level export list. **DELETE** `src/a2kit/capabilities.py`
  and `tests/test_capabilities.py`.
- **REMOVE** the lint-rule branch in
  `src/a2kit/packages/lint/rules/caps.py` that suggests `Cap.X`
  spellings (the whole rule if its only purpose was capability
  validation).

## Non-goals

- Touching `surfaces=` (handled in `replace-surfaces-with-visibility`).
- Touching `@a2kit.list_` parameter parity
  (handled in `list-verb-parameter-parity`).
- Changing what gets stamped into `meta.tags` by the framework.
  The decorator no longer accepts author tags; the framework still
  stamps verb tags. MCP filtering on `_meta` etc. unaffected.

## Migration

- Authors who set `tags={...}`: drop the kwarg. Zero in-repo callers.
- Authors importing `a2kit.Cap` / `a2kit.capabilities`: delete.
  Zero in-repo callers (confirmed by grep).

## Risk

XS. Pure deletions. Confirmed-unused via grep across `src/`, `tests/`,
`examples/`, and the four downstream consumer repos
(a2web, a2db, a2atlassian, fox).
