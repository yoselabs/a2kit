## Why

`serve --transport=http --select surface=mcp` is documented to serve the MCP
surface alone (`serve --select 'surface=mcp' serves MCP alone`). In practice it
does **not** remove the REST surface whenever the App registers a health check.
Verified against a live a2web MCP-only serve — `/api/openapi.json` still lists
`/api/ask`, `/api/fetch_raw`, `/api/refresh`, `/api/_meta.health`, `/api/health`.

Two compounding defects, both in `runtime.build()`'s selector application:

1. **The synthetic `_meta.*` tool escapes the selector.** `@app.health_check`
   installs `_meta.health`, whose router is re-bound to the runtime **after**
   `_apply_descriptor_selectors` has run (`runtime.py`). It keeps its
   LISTED-on-every-surface default, so `_surface_has_registrations(rt, "api")`
   stays `True` and `build_parent_app` mounts `/api`.

2. **Surface narrowing edits the derived projection, not the source of truth.**
   `_apply_descriptor_selectors` narrows a descriptor's `expose` tuple, but
   `expose` is a *derived* view of the surface matrix (`tool.py`:
   `mounted_surfaces(matrix_for(meta.extras))`). The matrix itself is left
   un-narrowed, and the FastAPI mount decision (`build_http_app._http_mountable`)
   reads the **matrix** (`advertised_on(matrix_for(...), "api")`), not `expose`.
   So once `/api` is mounted (defect 1), every tool still mounts on it.

Net: `--select surface=<x>` is **not** a surface boundary. This is
security-relevant — a2web's container plan (`deployable-container-ci` D5) relies
on `--select surface=mcp` to shrink the attack surface, and that guarantee is
false today.

## What Changes

- **Narrow the surface *matrix* (the single source of truth), not just the
  derived `expose`.** In `_apply_descriptor_selectors`, a `surface=` selector
  sets every excluded network surface (`mcp`/`api`) to `ABSENT` on the
  descriptor's `extras.surfaces` matrix and recomputes `expose` from it. Both
  surface builders (`build_http_app` reads the matrix, `build_mcp_server` reads
  `expose`) then agree. `cli` is not a `--select` target and is left untouched.
- **Apply the selector to the synthetic `_meta.*` descriptors** at their
  post-build re-bind, so `_meta.health` narrows like any other tool. Under
  `--select surface=mcp` it becomes MCP-only and no longer drags `/api` along.

Result: `--select surface=mcp` yields a genuinely MCP-only server (no `/api`
mount, no REST routes) even with a health check registered; `--select
surface=api` is the symmetric case.

## Capabilities

### Modified Capabilities

- `runtime-tool-selection`: the `surface=` selector SHALL narrow the source
  surface matrix (so every surface builder agrees) and SHALL apply to synthetic
  `_meta.*` tools, so selecting a surface actually removes the others.

## Non-goals

- Not changing the `--select` DSL, the `--tools=` name selector, or `verb=` /
  `name=` selectors.
- Not unifying `expose` and the matrix into one field (a larger refactor);
  `expose` stays a derived view, now kept consistent under selection.
