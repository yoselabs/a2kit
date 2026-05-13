# `@a2kit.list_` parameter parity with read/write/tool

## Why

The four verb decorators have asymmetric parameter sets:

| param            | `read` | `write` | `tool` | `list_` |
|------------------|:-:|:-:|:-:|:-:|
| `name`           | ✓ | ✓ | ✓ | ✓ |
| `reports`        | ✓ | ✓ | ✓ | ✓ |
| `visibility`     | ✓ | ✓ | ✓ | (this change adds) |
| `idempotent`     | ✓ | ✓ | ✓ | ✗ |
| `open_world`     | ✓ | ✓ | ✓ | ✗ |
| `title`          | ✓ | ✓ | ✓ | ✗ |
| `destructive`    | ⚠︎raises | ✓ | ✓ | ✗ |
| `annotations=`   | ✗ | ✗ | ✓ | ✗ |
| `*default_fields`| ✗ | ✗ | ✗ | ✓ |
| `page_size`      | ✗ | ✗ | ✗ | ✓ |
| `selectable_fields` | ✗ | ✗ | ✗ | ✓ |

The asymmetry is historical, not principled. The audit (explore
session 2026-05-13) re-framed `idempotent`, `open_world`, `title`,
and `destructive` as **transport-neutral semantic flags** (see
`adr-semantic-flag-vocabulary`). They describe properties of the
tool itself and have meaningful reads on every transport. A
list-shaped tool has the same semantic properties (it can be
`idempotent`, it has a `title`, etc.) — there is no reason the
decorator excludes them.

## What changes

Add four kwargs to `@a2kit.list_` that already exist on the other
three verbs, plus `visibility` (added in
`replace-surfaces-with-visibility`):

- **ADD** `idempotent: bool = False`
- **ADD** `open_world: bool = False`
- **ADD** `title: str | None = None`
- **ADD** `visibility: Visibility | None = None`

`destructive` is **not** added (a list is read-shaped and inherits
the `read`/`list_` "destructive=True raises" contract — same as
`read`).

`annotations=` is **not** added (the escape-hatch lives on
`@a2kit.tool` and is unused; `adr-semantic-flag-vocabulary` codifies
the four named flags as the canonical surface).

## Non-goals

- Touching `*default_fields` / `page_size` / `selectable_fields`
  (these are list-shape-specific; the other verbs don't need them).
- Renaming any existing parameter.
- Validation logic for the new kwargs — they pipe straight through
  to `_build_annotation_kwargs` like on the other verbs.

## Migration

None. Pure addition; default values match the prior implicit
behaviour (all four new fields are `None`/`False` defaults, which
produces the exact same `ToolAnnotations` shape `list_` stamps
today).

## Risk

XS. Backward-compatible kwarg addition. No behaviour change for
existing callers; new kwargs are opt-in.
