## 1. BDD-first — reproduce both defects

- [x] 1.1 Failing test: an App with `@app.health_check` + a projection tool,
      `build(app, select=["surface=mcp"])` → `build_parent_app` mounts `{"/mcp"}`
      only (today it also mounts `/api`). (`tests/packages/select/`)
- [x] 1.2 Failing test: under `surface=mcp`, the projection tool's *matrix* is
      narrowed — `advertised_on(matrix_for(desc._meta.extras), "api")` is False
      (today the matrix still advertises api, only `expose` was narrowed).
- [x] 1.3 Failing test: the synthetic `_meta.health` descriptor is narrowed —
      `expose == ("mcp",)` and its matrix drops api under `surface=mcp`.

## 2. Fix in `runtime.py`

- [x] 2.1 Add `_narrow_surface_matrix(matrix, selectors)` — set excluded network
      surfaces (`mcp`/`api`) to `ABSENT`; leave `cli`.
- [x] 2.2 In `_apply_descriptor_selectors`, for a matching descriptor with a
      `surface=` selector, rebuild it with the narrowed matrix (`extras.model_copy`
      + `replace(_meta=...)`) and `expose` recomputed from the narrowed matrix.
- [x] 2.3 Run `_apply_descriptor_selectors` over the re-bound `_meta.*`
      descriptors before extending `descriptors` / `_descriptor_by_name`.

## 3. Verify

- [x] 3.1 New tests green; existing select tests
      (`test_surface_mcp_select_skips_fastapi_mount`, `..._api_...`,
      `..._empty_...`) stay green.
- [ ] 3.2 Live check against a2web (post-release, after pin bump): `a2web serve
      --transport=http --select surface=mcp` → `/api/openapi.json` is 404 and
      `curl /health` → 200.
- [x] 3.3 `make test` (90% cov gate) + ruff + ty-src + a2kit-static green.

## 4. Docs + spec + release

- [x] 4.1 `runtime-tool-selection` spec: ADDED requirement (surface selector is
      matrix-authoritative + applies to `_meta.*`).
- [x] 4.2 `CHANGELOG.md` entry (fix; new minor).
- [x] 4.3 `openspec validate --strict` green; version bump; tag; push.
- [ ] 4.4 a2web `deployable-container-ci` D5 note: clear the ⚠ once the a2kit pin
      picks up the fix (bump + relock). (post-release)
