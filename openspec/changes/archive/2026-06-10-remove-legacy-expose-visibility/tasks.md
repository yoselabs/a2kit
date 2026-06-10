# Tasks — remove-legacy-expose-visibility

## 1. Specs (define the post-removal surface)

- [x] 1.1 Spec deltas: `surfaces-projection` (REMOVE legacy-mapping requirement;
      `surfaces=` is sole input, default LISTED-everywhere, Router `surfaces`
      ClassVar default), `verb-decorators` (decorators reject `expose=`/
      `visibility=` with the plain unexpected-kwarg `TypeError`),
      `multi-surface-authoring` (re-express in `surfaces=` vocabulary).
- [x] 1.2 `openspec validate remove-legacy-expose-visibility --strict` passes.

## 2. Tests RED (post-removal behavior, watch fail)

- [x] 2.1 Add `test_expose_visibility_kwargs_removed`: `@a2kit.read(expose=...)`
      and `@a2kit.read(visibility=...)` each raise `TypeError` naming the kwarg
      as unexpected (plain signature rejection, no bespoke hint).
- [x] 2.2 Add a default-placement test: a verb with no `surfaces=` is LISTED on
      every surface (mcp/api/cli) — "available on all surfaces by default".
- [x] 2.3 Run; confirm 2.1 fails against the still-present kwargs.

## 3. Migrate existing tests to `surfaces=` (per design D3)

- [x] 3.1 Translate every `expose=` / `visibility=` call site in `tests/`
      (~68 across ~17 files) using the D3 mapping — preserving CLI presence
      (`expose=("mcp",)` → `surfaces=("mcp","cli")`, etc.), NOT a blind rename.
- [x] 3.2 Migrate the 3 class-level `visibility = "cli"` Router defaults to
      per-verb `surfaces = ("cli",)` on each restricted verb (no Router-level
      default replaces the ClassVar — D1).
- [x] 3.3 Remove the now-moot "surfaces= cannot combine with legacy
      expose=/visibility=" mutual-exclusion test.

## 4. Remove the legacy input path (GREEN)

- [x] 4.1 `_verbs.py`: drop `expose` / `visibility` params from `read`/`write`/
      `list_` + `_stamp`; remove the mutual-exclusion branch; `surfaces=`
      (UNSET → default matrix) is the only path; always store `extras.surfaces`
      + derived `extras.expose`.
- [x] 4.2 `_surfaces.py`: delete `_resolve_legacy`, `legacy_expose` /
      `legacy_visibility` params on `resolve_surfaces`, and the legacy branch in
      `matrix_for` (always read `extras.surfaces`).
- [x] 4.3 `metadata.py`: drop the `visibility` field from `A2KitMetaExtras`
      (keep `expose` as the derived normalized field).
- [x] 4.4 `routers.py` + `app.py`: delete the `visibility` ClassVar default and
      its application loops (`meta.extras.visibility = type(self).visibility`;
      app-level `= "all"`) — no replacement (D1).
- [x] 4.5 `packages/lint/rules/surface.py`: rewrite `AK211` to prescribe an
      explicit `surfaces=` on credential-named tools (D2); update its docstring
      + the `_has_*_kwarg` check.
- [x] 4.6 `packages/runtime_tools.py`: update `visibility="hidden"` prose to the
      `surfaces` unlisted vocabulary (logic already reads the matrix).
- [x] 4.7 `packages/lint/rules/purity.py`: drop the `"visibility"` reference if
      it names the removed kwarg.

## 5. Verify

- [x] 5.1 Full suite green; `make lint` green (ruff / ty src / a2kit-lint static
      incl. the rewritten AK211 / all three drift gates / openspec-validate /
      surface snapshots). Regen `surface-snapshot` if the Tier surfaces changed
      (they should not — `surfaces`/`expose`/`visibility` are decorator-local).
- [x] 5.2 Confirm `grep -rn "expose=\|visibility=" src/ tests/ examples/` returns
      only the new `surfaces`-vocabulary lint-rule references, zero legacy kwargs.

## 6. Release

- [x] 6.1 Archive the change (applies spec deltas to canonical).
- [x] 6.2 CHANGELOG: new `### Changed — Removed legacy expose=/visibility=` entry
      under a fresh `## Unreleased`, with the D3 mapping table; correct the
      v0.42.0 entry's false "DeprecationWarning shim" / "replaced" wording.
- [x] 6.3 Cut `v0.42.1` (bump pyproject + uv.lock, tag, push main + tag). a2web
      targets `v0.42.1`.
