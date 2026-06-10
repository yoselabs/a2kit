# remove-legacy-expose-visibility

## Why

ADR 0028 Wave 2 introduced the `surfaces=` projection axis to replace the
`expose=` / `visibility=` pair, but the old kwargs were **kept as a silent
backward-compat shim** (`_surfaces._resolve_legacy`): `@a2kit.read(expose=...)`
/ `visibility=` still work, mapped forward with **no warning and no error**.

That is precisely the anti-pattern `AGENTS.md` §1 exists to prevent —
"graceful migration paths hide drift from consumer read paths." It is also
silent (§3) and redundant (§2): two ways to place a verb on surfaces, one of
them invisible. The v0.42.0 CHANGELOG even mis-describes it as a
"DeprecationWarning shim" — there is no warning.

Under the tombstone sunset rule, a transitional surface must be **fail-loud**,
not silently working. The live consumer (a2web) is migrating to v0.42.x now, so
this is the moment to remove the shim entirely and let a2web fail loud at
type-check / lint time that `expose=` / `visibility=` no longer exist — forcing
the migration into a2web's commit history, exactly as §1 intends. No tombstone
hint is added: the kwargs simply do not exist (language-default `TypeError`).

## What Changes

- **Remove the `expose=` and `visibility=` kwargs** from `@a2kit.read` /
  `@a2kit.write` / `@a2kit.list_` (and `_stamp`). `surfaces=` is the sole
  surface-placement input. Omitted `surfaces=` defaults to LISTED on every
  registered surface (`("mcp","api","cli")`) — identical to the old
  `expose=("mcp","api")` + `visibility="all"` default, so the no-kwargs case is
  unchanged.
- **Delete `_resolve_legacy`** + the `legacy_expose` / `legacy_visibility`
  parameters in `a2kit._surfaces`, and the legacy branch in `matrix_for` /
  `_stamp`. The surface matrix is always resolved from `surfaces=` at decoration
  time; `extras.surfaces` is always populated.
- **Drop the `visibility` field** from `A2KitMetaExtras`. `extras.expose`
  (derived via `mounted_surfaces(matrix)`) stays as the internal normalized
  field every adapter already reads — only the legacy *input* path goes.
- **Drop the Router/App-level `visibility` ClassVar default** entirely, with no
  replacement (decision D1): an omitted `surfaces=` already defaults to LISTED on
  every surface, so a verb is available on all surfaces by default; the rare
  "restrict the whole router" case is expressed per-verb with `surfaces=(...)`.
  One placement axis, no second mechanism.
- **Rewrite the `AK211` lint rule** (`A2K-SURFACE-EXPLICIT`, `surface.py`):
  credential-named tools SHOULD declare an explicit `surfaces=` (so they don't
  default onto the network), replacing its old "SHOULD declare `visibility=`"
  prescription (decision D2).
- **Migrate the ~68 `expose=` / `visibility=` call sites in `tests/`** (and 3
  class-level `visibility=` Router defaults) to `surfaces=`, per the mapping in
  design.md. a2kit's `examples/` already use `surfaces=` / defaults — no change.

## Capabilities

### Modified Capabilities

- `surfaces-projection`: rewrite the "old `(expose, visibility)` pair maps mechanically" requirement — the pair is removed (no shim, no `DeprecationWarning`, plain `TypeError`); the mapping stays as the CHANGELOG migration recipe with the CLI-presence bug fixed.
- `verb-decorators`: the verb decorators SHALL NOT accept `expose=` / `visibility=` (drop from `list_`'s signature too); passing either raises the language-default unexpected-kwarg `TypeError`; the Router `visibility` ClassVar is retired with no class-level surface default.
- `surface-protocol`: the removed decoration-time `a2kit._verbs._validate_expose` citation is replaced by the build-time `a2kit.runtime._validate_descriptor_expose` reality (unknown-surface names rejected at `runtime.build()`); the mounted-surfaces tuple derives from the resolved `surfaces=` matrix.

(`multi-surface-authoring` only references `expose=` in intro prose, not in a requirement — no delta; the prose is stale but ungated.)

## Impact

- **Code:** `_verbs.py`, `_surfaces.py`, `metadata.py` (drop `visibility` field), `routers.py` + `app.py` (visibility ClassVar → surfaces ClassVar default), `packages/lint/rules/surface.py` (AK211 rewrite), prose in `packages/runtime_tools.py`.
- **Tests:** ~17 files / ~68 kwarg sites migrated to `surfaces=`; the "surfaces= cannot combine with legacy expose=/visibility=" mutual-exclusion test is removed (no legacy kwargs to conflict with); add a test asserting `expose=`/`visibility=` raise the plain unexpected-kwarg `TypeError`.
- **Consumer break (a2web):** `@a2kit.read(expose=...)` / `visibility=` stop working — fail loud at ty / a2kit-lint / runtime. This is the intended forcing function; a2web migrates to `surfaces=` as part of its v0.42.x upgrade. Documented in the CHANGELOG with the mapping table.
- **Out of scope:** the other graceful shims surfaced in the same audit (`SURFACE_REGISTRY` module proxy, `AmbientContextMissing` one-release shim, `LEGACY_CODE_ALIASES` lint-code window) — tracked separately; each has its own horizon.
