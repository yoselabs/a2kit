## Why

[[add-substrate-dep-class]] taught the splitter to route FastAPI `Depends` / `Security` markers through to FastAPI's signature, but FastAPI still cannot resolve a2kit container types: `Container.expose_as_fastapi_depends(T)` doesn't exist, and `fastapi_app.dependency_overrides` isn't populated for container-known types. ADR 0020 documents this gap as a hard limitation. The user pin (2026-05-23) explicitly requires it close: "DI must be available everywhere, compatible with FastAPI DI — security handlers will need to consume some deps."

This change closes the gap with a single bridge surface on the container plus a wiring step in `build_http_app`. Carved out of the [[bridge-di-to-substrate-native]] umbrella as a single-cycle change with one obvious test (a FastAPI `Security` guard that consumes both a `Principal` and a container-known `Database`).

## What Changes

- ADD `Container.expose_as_fastapi_depends(type_: type) -> Callable[..., Any]` returning a zero-arg callable usable as a FastAPI `Depends(...)` dependency. The returned callable reads the active `_a2kit_scope` contextvar and returns `scope.get(type_)`. Called outside any active scope it raises `RuntimeError("a2kit Depends resolver called outside call_scope")`.
- CACHE generated callables per type on the container (`_fastapi_depends_cache: dict[type, Callable]`).
- WIRE in `packages/http/build.py:build_http_app`: for every container-known type referenced by any descriptor's `wire_param_names` or `substrate_dep` chain, call `expose_as_fastapi_depends(T)` and register the result in `fastapi_app.dependency_overrides`.
- ENSURE the per-call `_a2kit_scope` is open BEFORE any FastAPI dependency callable runs (the wrapper body already opens scope; verify ordering vs FastAPI's dep-resolution).
- DISCHARGE ADR 0020 `dependency_overrides[T]` no-op clause: amendment note added at the bottom of the ADR pointing to this change.

## Impact

- Affected specs: NEW `di-substrate-bridge` capability; MODIFIED `di-container-package` (gains `expose_as_fastapi_depends`); MODIFIED `http-surface` (bridge wired in build).
- Affected code: `packages/di/container.py`; `packages/http/build.py`; `docs/adr/0020-multi-surface-authoring.md` (supersedence note).
- Breaking: previously documented "dep overrides are a no-op for a2kit types" stops being true. Tests asserting the gap (`tests/packages/http/test_dependency_override.py`) must be rewritten to assert the bridge works.
- Depends on: [[add-substrate-dep-class]] (needs `substrate_dep` field on descriptors / SplitSignature).
- Unblocks: [[propagate-principal-and-authorize]] (needs the bridge to register `Principal`).
