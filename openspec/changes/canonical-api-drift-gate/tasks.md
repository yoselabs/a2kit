# Tasks — canonical-API drift gate

## 0. Prerequisites

- [ ] 0.1 Baseline: `make test` + `make lint` green. v0.33's
      `tests/test_readme_symbol_drift.py` passes.
- [ ] 0.2 Read the existing drift gate to understand its parse
      shape — extension should reuse the same scanning approach
      where possible.

## 1. Define the canonical-type allowlist

- [ ] 1.1 In `tests/test_readme_symbol_drift.py` (or a new helper
      module), declare:
      ```python
      CANONICAL_TYPES = {
          "TestClient": "a2kit.testing.client.TestClient",
          "App": "a2kit.app.App",
          "Router": "a2kit.routers.Router",
          "ToolContext": "fastmcp.Context",  # re-exported as a2kit.ToolContext
      }
      CANONICAL_DECORATORS = {"read", "write", "list_"}
      ```
- [ ] 1.2 Resolve each entry at test-import time to a live type
      object. Skip cleanly with a `pytest.skip(...)` if any import
      fails (so import errors don't masquerade as drift failures).

## 2. Parse method references in README code blocks

- [ ] 2.1 Walk fenced ```python``` blocks in `README.md`. For each
      block, AST-parse the body and walk for `ast.Attribute`
      nodes. Extract `(obj_name, attr_name)` pairs where `obj_name`
      ∈ `CANONICAL_TYPES` (treating variable names as type
      references — e.g. `client.call` → assume `client: TestClient`).
- [ ] 2.2 For each pair, assert `hasattr(canonical_types[obj_name],
      attr_name)`. Collect failures into a list and fail with one
      structured error message listing every drift hit.
- [ ] 2.3 Handle the variable-name-to-type mapping with a small
      registry per README: when a code block contains
      `client = a2kit.testing.client(app)`, register `client` as
      `TestClient` for the remainder of that block.

## 3. Add tests/test_canonical_apis.py

- [ ] 3.1 Create `tests/test_canonical_apis.py`. Fixture: a tiny
      single-router app with one read tool.
- [ ] 3.2 Exercise the documented call shapes end-to-end:
      - `client.call(tool, **kwargs)` and `client.invoke(tool, **kwargs)`
        — both must return equivalent shapes
      - `client.call_wire(tool, **kwargs)` — returns wire-encoded
        payload
      - `app.singleton(T, factory)` and `app.singleton(T, factory, teardown=...)`
      - `@a2kit.read()`, `@a2kit.write(destructive=False)`,
        `@a2kit.list_()` — all decorate a method cleanly
      - `Router` subclass declaration with `slug = "x"`, `tools = (...)`
- [ ] 3.3 Each call shape is exactly one test. Failure messages
      point at the README section claiming the shape.

## 4. Spec delta — docs-code-parity

- [ ] 4.1 Author `openspec/changes/canonical-api-drift-gate/
      specs/docs-code-parity/spec.md`:
      - ADDED Requirement: "Canonical-type method drift gate"
      - ADDED Requirement: "Canonical-API call-shape exerciser"
      - Scenarios for: rename caught at CI; new method on a
        canonical type doesn't need to be added to the gate (only
        drift is caught)

## 5. Wire into make lint

- [ ] 5.1 The existing `make lint` already runs
      `pytest tests/test_readme_symbol_drift.py`. Extend that
      command to include `tests/test_canonical_apis.py` (or add a
      separate invocation in the Makefile).
- [ ] 5.2 Confirm both tests run in the lint stage; failure breaks
      `make lint`.

## 6. Verify

- [ ] 6.1 `make test` green; the two new tests pass.
- [ ] 6.2 `make lint` green; the new lint stages pass.
- [ ] 6.3 Smoke: temporarily rename `TestClient.invoke` to
      `_invoke` (locally). Verify both the drift gate AND
      `test_canonical_apis.py` fail. Revert the local rename.
      Confirms both tests have teeth.

## 7. Out-of-scope

- [ ] 7.1 Static type-checking of README code blocks. Too brittle;
      typers diverge across Python versions and FastMCP versions.
- [ ] 7.2 Extending to `OPERATIONAL_CONTRACTS.md` and
      `examples/*/README.md`. The first pass scopes to `README.md`;
      expand iteratively if drift surfaces in the others.
