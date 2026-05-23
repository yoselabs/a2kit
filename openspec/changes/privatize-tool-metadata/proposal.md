## Why

`a2kit.metadata.get_meta` / `set_meta` are public symbols read from ~25 sites in `src/` and ~35 sites in `tests/`. Every read reaches across the descriptor abstraction, treating `A2KitMeta` as a parallel surface to `ToolDescriptor`. This both duplicates the "tool shape" projection (substrate adapters read meta directly) and prevents future refactors (e.g. moving annotation-kwarg merging out of `_verbs.py`) from being internal.

With `ToolDescriptor` now carrying `metadata_view` and `annotations_view` ([[extend-descriptor-fields]]) and substrate adapters consuming descriptors via `runtime.descriptor_for(...)` ([[defer-descriptor-materialization]]), `get_meta`/`set_meta` no longer need to be public. Privatising them lets us enforce a single read surface (`ToolDescriptor` via `AppRuntime`) and unblocks moving `_stamp`/`_compute_report_schema`/`_build_annotation_kwargs` helpers to where they belong.

## What Changes

- RENAME `metadata.get_meta` → `metadata._get_meta`; `metadata.set_meta` → `metadata._set_meta`.
- ADD migration-hint raises at the old public names: `def get_meta(*a, **kw): raise AttributeError("metadata.get_meta is private since privatize-tool-metadata; read tool data via ToolDescriptor (runtime.descriptor_for(name))")`. Same for `set_meta`.
- SWEEP all internal callers in `src/a2kit/packages/**` to consume `runtime.descriptor_for(name)` instead of `get_meta(fn)`. The allowlist for the underscored names is `{a2kit._verbs, a2kit.metadata, a2kit.runtime, a2kit.tool, a2kit.app, a2kit.routers, a2kit.schema}` — the modules that legitimately need to read/write meta during composition.
- RELOCATE module-private helpers currently in `_verbs.py`:
  - `_stamp(fn, meta)` and `_compute_report_schema(...)` → `metadata.py` as module-private helpers.
  - `_build_annotation_kwargs(...)` and `_kwargs_for(...)` → `_verb_validators.py`.
  - `_verbs.py` keeps decorator factories (`read`, `write`, `list_`) and public verb-level validators only.
- ADD lint rule `A2K-METADATA-PRIVATE`: AST-scan; any `from a2kit.metadata import _get_meta|_set_meta` outside the allowlist is a hard error.
- REWRITE tests: ~35 sites switch from `get_meta(fn)` to a fixture helper `descriptor_for(app, name)` that calls `app.build()` and reads from the runtime. (Tests asserting decorator-time stamping pre-`build()` can use `a2kit.metadata._get_meta` directly, since they live in the test package which becomes part of the allowlist for test-only purposes — or, preferably, switch to building the App.)

## Impact

- Affected specs: `tool-descriptors` (MODIFIED — meta is private), `verb-decorators` (MODIFIED — public read API is `ToolDescriptor` only), `module-layout-discipline` (MODIFIED — add `A2K-METADATA-PRIVATE`)
- Affected code: `src/a2kit/metadata.py`, `src/a2kit/_verbs.py`, `src/a2kit/_verb_validators.py`, `src/a2kit/packages/**` (cutover), `src/a2kit/packages/lint/rules/`, `tests/**` (~35 sites)
- Breaking: YES (public `get_meta`/`set_meta` removed). Internal-only surface per AGENTS §1; documented loud-crash via migration hint.
- Depends on: [[extend-descriptor-fields]], [[defer-descriptor-materialization]]
