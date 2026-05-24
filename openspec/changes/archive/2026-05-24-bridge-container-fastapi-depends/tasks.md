## 1. BDD first

- [x] 1.1 `tests/packages/http/test_di_bridge.py`: a FastAPI `Security` guard `def guard(*, db: Database) -> str: return db.name` registered on a route resolves `db` from the a2kit container. Concurrent requests get isolated scope instances (SCOPED provider gives different objects per request).
- [x] 1.2 `tests/packages/di/test_expose_as_fastapi_depends.py`: callable invoked outside any active `_a2kit_scope` raises `RuntimeError("a2kit Depends resolver called outside call_scope")`. Cache is per-type identity-stable.

## 2. Container surface

- [x] 2.1 Add `Container.expose_as_fastapi_depends(type_) -> Callable[..., Any]` that returns the generated zero-arg resolver. Implementation reads `_a2kit_scope.get()` (existing contextvar; verify name) and returns `scope.get(type_)`.
- [x] 2.2 Cache on container in `_fastapi_depends_cache: dict[type, Callable]`. Cache key is the type identity; second call for same type returns the same callable.
- [x] 2.3 Raise `RuntimeError` with the documented message when no active scope.

## 3. HTTP build wiring

- [x] 3.1 In `build_http_app(runtime)`: after the FastAPI app is constructed but before route registration, collect the union of all `wire_param_names` ∪ `substrate_dep`-referenced types across descriptors. Filter to types known to the container.
- [x] 3.2 For each, call `container.expose_as_fastapi_depends(T)` and register the result in `fastapi_app.dependency_overrides[T] = resolver`.
- [x] 3.3 Verify ordering: wrapper body opens `call_scope` before FastAPI dep-resolution. If not, hoist the scope-open into a FastAPI middleware so it runs before `Depends` callables. Either way, BDD test in 1.1 is the gate.

## 4. ADR 0020 discharge

- [x] 4.1 Append a "Supersedence" note to `docs/adr/0020-multi-surface-authoring.md`: the `dependency_overrides[T]` no-op clause is closed by this change. Cross-link to the change archive directory once archived.
- [x] 4.2 Update / replace `tests/packages/http/test_dependency_override.py` (if it exists asserting the gap) to assert the bridge resolves.

## 5. Spec sync

- [x] 5.1 New spec `openspec/specs/di-substrate-bridge/spec.md`.
- [x] 5.2 Modify `openspec/specs/di-container-package/spec.md`: gain `expose_as_fastapi_depends`.
- [x] 5.3 Modify `openspec/specs/http-surface/spec.md`: build wires the bridge.

## 6. Final gates

- [x] 6.1 `openspec validate --strict bridge-container-fastapi-depends` passes.
- [x] 6.2 `make lint` green.
- [x] 6.3 `make test` green.
- [x] 6.4 Cold-start budget unaffected.
