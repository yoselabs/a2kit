## 1. Kernel-layer name registry

- [x] 1.1 Create `src/a2kit/_surface_names.py` with a private list and two functions: `register_surface_name(name)` and `registered_surface_names() -> tuple[str, ...]`
- [x] 1.2 Add the new module to `_KERNEL_MODULES` in `src/a2kit/packages/lint/layers.py`
- [x] 1.3 Unit test the new module: register, query, idempotent re-register

## 2. Wire registry side-effect

- [x] 2.1 In `src/a2kit/packages/dispatch/surface.py` (or wherever `SurfaceRegistry.register_surface` lives), call `register_surface_name(s.name)` after the existing duplicate-name guard succeeds
- [x] 2.2 Verify ordering: import `a2kit.packages.mcp` then `a2kit.packages.http`; assert `registered_surface_names() == ("mcp", "api")`

## 3. Verb decorator migration

- [x] 3.1 Replace `allowed = frozenset({"mcp", "api"})` in `src/a2kit/_verbs.py:111` with `allowed = frozenset(registered_surface_names())`
- [x] 3.2 Update the error message to enumerate the live registered names and include the "import a surface-mounting package" hint when empty
- [x] 3.3 Apply the same change to any sibling validation path on `@a2kit.write` and `@a2kit.list_` if it duplicates the literal

## 4. Tests

- [x] 4.1 Add scenario: registered surface is accepted (verb-decorators spec scenario 1)
- [x] 4.2 Add scenario: unregistered surface raises with enumerated message (scenario 2)
- [x] 4.3 Add scenario: synthetic `StubSurface("test")` registers and is accepted (scenario 3)
- [x] 4.4 Add scenario: empty registry raises actionable message (scenario 4) — needs a fixture that runs in a fresh subprocess or that monkey-clears the registry
- [x] 4.5 Add scenario: name registry layer-clean (surface-protocol spec scenario 2) — covered by existing `A2K-LAYER` test if the new module is in `_KERNEL_MODULES`

## 5. Validation

- [x] 5.1 `make lint` clean
- [x] 5.2 `openspec validate --changes --strict` passes for `surface-set-from-registry`
- [x] 5.3 Grep src/a2kit/ for any remaining `frozenset({"mcp"`, `"mcp", "api"`, or similar literals; remove if found
