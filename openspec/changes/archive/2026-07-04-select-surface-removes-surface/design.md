# Design — `--select surface=X` must remove the other surfaces

## Root cause (deterministic repro)

`build(a2web_app, select=["surface=mcp"])` then inspect:

```
ask          expose=('mcp',)          # projection tools narrow correctly...
fetch_raw    expose=('mcp',)
refresh      expose=('mcp',)
_meta.health expose=('mcp', 'api')    # ...but the meta tool keeps api
api_surface: None                     # author @app.api routes dropped (ok)
has api regs: True                    # _meta.health drags /api back in
```

Two independent bugs, in `a2kit/runtime.py`:

1. **Meta re-bind bypasses the selector.** The `_meta` health router is rebuilt
   and appended to `descriptors` *after* `_apply_descriptor_selectors` ran, so
   its descriptor is never filtered/narrowed.

2. **`expose` ≠ matrix under selection.** `expose` is derived once at descriptor
   build (`tool.py`: `mounted_surfaces(matrix_for(meta.extras))`). The selector
   narrows the stored `expose` tuple but not `extras.surfaces`. Readers split:

   | Reader | Source | After `surface=mcp` |
   |---|---|---|
   | `_surface_has_registrations` (mount y/n) | `desc.expose` | narrowed ✓ |
   | `build_mcp_server` tool loop | `desc.expose` | narrowed ✓ |
   | `build_http_app._http_mountable` | `matrix_for(extras)` | **un-narrowed ✗** |

   So once `/api` is mounted (bug 1), the http builder reads the un-narrowed
   matrix and mounts every tool on `/api`.

## Fix

Narrow the **matrix** (the source of truth) in `_apply_descriptor_selectors`;
`expose` recomputes from it. Then every reader agrees, and bug 2 is closed at
the source (no need to touch `build_http_app`).

```python
def _narrow_surface_matrix(matrix, selectors):
    # Network surfaces only — cli is not a --select target, leave it.
    out = dict(matrix)
    for s in selectors:
        if s.category != "surface":
            continue
        for surf in ("mcp", "api"):
            if surf in out and ((s.include and surf not in s.include) or surf in s.exclude):
                out[surf] = ABSENT
    return out
```

For a matching descriptor, rebuild it with the narrowed matrix on a copied
`extras` and a recomputed `expose`:

```python
new_matrix = _narrow_surface_matrix(matrix_for(meta.extras), selectors)
new_extras = meta.extras.model_copy(update={"surfaces": new_matrix})
new_meta   = replace(meta, extras=new_extras)
new_expose = tuple(s for s in mounted_surfaces(new_matrix) if s != "cli")
desc       = replace(desc, _meta=new_meta, expose=new_expose)
```

Close bug 1 by running the same selector pass over the meta descriptors at their
re-bind:

```python
meta_descs = _apply_descriptor_selectors(meta_descs, compiled_selectors)
```

`_apply_descriptor_selectors`'s existing "empty `expose` → drop" guard is kept:
`.matches` already guarantees a matching descriptor retains ≥1 included surface,
so a selected tool never drops spuriously.

## Why matrix-authoritative (not expose-authoritative)

Per ADR 0028, `surfaces=` (the matrix) is *the* placement axis; `expose` is a
compat projection (network surfaces only, ADR-0028 `tool.py` comment). Fixing at
the matrix keeps the one source of truth authoritative and makes the two network
surface builders converge without special-casing either. The alternative —
teaching `build_http_app` to also read `expose` — would entrench the divergence
and leave the MCP side (which reads `expose`) and the FastAPI side (matrix)
permanently out of step.

## Blast radius

- `--select surface=mcp` with a health check → `/api` no longer mounts (the bug).
- `--select surface=mcp` without a health check → unchanged (already worked;
  existing `test_surface_mcp_select_skips_fastapi_mount` stays green).
- No selector → `_apply_descriptor_selectors` returns early; zero change.
- `--tools=` / `verb=` / `name=` selectors → untouched (only `surface=` narrows
  the matrix).
- CLI surface state in the matrix is preserved (cli is not a `--select` target).

## Relationship to the refounding (ADR 0032)

`--select` / multi-surface is framework-era machinery ADR 0032 will eventually
retire. But it ships today and a2web relies on it as a **security boundary**, so
a correctness fix now is warranted (same reasoning as the v0.48.0 liveness
route). No new surface; a bug fix on the existing selector.
