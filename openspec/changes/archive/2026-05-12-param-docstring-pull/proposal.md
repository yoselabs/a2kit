# Pull parameter descriptions from the tool docstring

## Why

Round-5 a2web feedback (gap 4) and the round-6 status check flagged that
real routers — a2web's `routers.py` is the canonical example — are
**~80% `Annotated[T, a2kit.Param(description=...)]` wrappers**. Almost
every one of those `Param(...)` calls just restates a description that
**already lives one line above** in the function's `Args:` docstring
block. Two sources of truth for the same string, every signature
visually buried under wrapper noise, and the author pays the tax on
every new kwarg.

The docstring is already canonical for the **tool** description (see
the existing `tool-description-contract` spec, "Docstring drives tool
description"). Extending the same contract one level down — per
parameter — removes the wrapper for the common case while leaving
`Param` available for the cases where it genuinely earns its keep
(description differs from docstring, or non-description schema
metadata like `examples=`, `ge=`, `le=`).

## What Changes

- `@a2kit.read` / `@a2kit.write` / `@a2kit.tool` / `@a2kit.list_`
  SHALL parse the function's docstring at decoration time and extract
  per-parameter descriptions from a Google-style `Args:` (alias `Arguments:`,
  `Parameters:`) section. Extracted descriptions are baked into
  `A2KitMeta` and applied as if the parameter carried
  `Annotated[T, Param(description=...)]`.
- Precedence: an **explicit** `a2kit.Param(description=...)` (or any
  pydantic `Field` carrying a `description=` in the `Annotated[...]`
  metadata) on a parameter SHALL win over any docstring entry. The
  docstring is a fallback, never an override.
- A parameter with no `Annotated` metadata and no docstring entry SHALL
  remain undescribed — this is current behaviour.
- `a2kit.Param` itself stays. Its description-only call sites become
  optional (drop them in favour of the docstring); its constraint /
  examples call sites are unaffected. No deprecation, no removal.
- Docstring parsing is **decoration-time only**. The resolved
  description string is stored on `A2KitMeta`; there is no per-call
  parsing cost. Docstring style other than Google-style (Numpy,
  Sphinx, reST `:param:`) is an explicit **non-goal** for this change.
- No new third-party dependency. The Google-style `Args:` block is
  small enough to parse with a hand-rolled helper (≈30 LOC) using
  `inspect.cleandoc` plus indentation-aware iteration.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `tool-description-contract`: extend the docstring-is-canonical rule
  to cover per-parameter descriptions; pin Google-style `Args:` as
  the supported format; pin precedence rules between docstring and
  explicit `Param`/`Field` metadata.
- `router-conventions`: state that router tool methods may rely on
  the docstring for parameter descriptions and SHOULD do so when the
  description is the only `Param` field being used.

## Impact

- **Affected modules** — `src/a2kit/tool.py` (`_stamp` grows a
  docstring-pull step before constructing `A2KitMeta`),
  `src/a2kit/params.py` (a tiny resolver helper, or a new sibling
  `src/a2kit/_docstring.py`), `src/a2kit/metadata.py`
  (`A2KitMeta` carries an optional `param_descriptions: Mapping[str, str]`
  field so the MCP schema builder and CLI option builder can consume
  it alongside `Annotated[...]` metadata).
- **Public API** — purely additive. Existing `Annotated[T, Param(...)]`
  call sites continue to work unchanged and still win on conflict.
- **Consumers** — a2web's `routers.py` is the main beneficiary;
  in-repo `examples/` should be migrated opportunistically (not in
  scope for this change beyond the demo case used in the BDD scenario).
- **Dependencies** — none added. No `docstring-parser`, no `griffe`.
- **Tests** — covered by new scenarios under both modified specs;
  implementation-level tests land alongside the code change, not in
  this proposal.
