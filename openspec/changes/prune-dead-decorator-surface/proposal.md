# Prune dead decorator surface

## Why

A consumption-interface audit (explore session 2026-05-13) measured
real usage of every public kwarg across all six example apps and the
in-repo test suite. Three surfaces have **zero live readers** and
inflate every author's IDE autocomplete with knobs nobody turns:

- **`tags=`** kwarg on `@a2kit.read/write/list_/tool`. Author-set tags
  never appear in any example, downstream consumer, or test fixture.
  The MCP server reads `meta.tags`, but every tag it cares about is
  framework-auto-stamped (`"read"`, `"write"`, `"list"`, `"_meta"`).
  No author has ever set the kwarg.
- **`Cap` enum + `capabilities` registry** in `a2kit.capabilities`.
  The grep is conclusive: appears in its own unit test, in one
  lint-rule "did you mean Cap.X?" suggestion string, and nowhere else.
  No decorator usage, no consumer reads, no runtime contract. Pure
  aspirational surface.
- **`App(..., debug=False)`** constructor flag. Stored on
  `self.debug` and never read by any production code, test, or
  example.

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
- **REMOVE** `debug` kwarg from `App.__init__` and `self.debug`
  attribute.

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
- Authors passing `debug=True`: drop. Zero readers regardless.

## Risk

XS. Pure deletions. Confirmed-unused via grep across `src/`, `tests/`,
`examples/`, and the four downstream consumer repos
(a2web, a2db, a2atlassian, fox).
