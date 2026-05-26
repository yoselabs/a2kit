## 1. Add `Container.seed_scoped` (foundation)

- [x] 1.1 Add `Container.seed_scoped(type_, value)` to
  `src/a2kit/packages/di/container.py`. Refuse to operate on a root
  container (parent is None) with a clear `TypeError`. Register
  `_providers[type_]`, `_scope_metadata[type_] = Scope.SCOPED`,
  `_scoped_cache[type_] = value`.
- [x] 1.2 Unit tests at `tests/packages/di/test_seed_scoped.py`:
  child-only restriction, last-write-wins on same type, retrieval
  via `await child.get(type_)`, retrieval via `resolve_params` on a
  function declaring the type.
- [x] 1.3 Public-surface doc: add `seed_scoped` to the
  `Container` docstring's "Public API" section; update
  `packages/di/__init__.py` re-exports if any.

## 2. Create `_principal_bridge.py` (the named bridge — clean break)

- [x] 2.1 Create `src/a2kit/packages/dispatch/_principal_bridge.py`
  with:
  - module-private `_request_principal: ContextVar[Principal | None]`
    (the ONLY declaration; no shim in `packages/context`)
  - `set_request_principal(p: Principal) -> Token`
  - `reset_request_principal(token: Token) -> None`
  - `current_request_principal() -> Principal | None`
  - `__all__ = ["set_request_principal", "reset_request_principal",
    "current_request_principal"]`
- [x] 2.2 Remove the declaration from
  `src/a2kit/packages/context/principal.py` in the same commit.
  No re-export, no shim, no backward-compat path.
- [x] 2.3 Unit tests at
  `tests/packages/dispatch/test__principal_bridge.py`: writer +
  reader symmetry, reset restores prior state, nested
  set+reset semantics.

## 3. Migrate substrate writers to the named API

- [x] 3.1 `src/a2kit/packages/auth/api_key.py`: replace direct
  ContextVar set/reset with `set_request_principal` /
  `reset_request_principal`.
- [x] 3.2 `src/a2kit/packages/auth/testing.py:using_principal`:
  **DELETE** the contextmanager entirely. Find every test that
  imports it (`grep -rn 'using_principal' tests/ src/`) and migrate
  inline — `App`-bearing tests use
  `app.container().provide(Principal, fake)`; others call the
  named bridge writer API directly.
- [x] 3.3 `src/a2kit/packages/mcp/principal_middleware.py`: ditto.
- [x] 3.4 `src/a2kit/packages/http/build.py:_apply_authorize_gate`:
  simplify per design Decision 7 — the kwargs-scan-and-stuff dance
  is deleted; `_lift_principal_into_scope` upstream already
  published via the named bridge, so no re-publication is needed
  inside the gate wrapper.
- [x] 3.5 `src/a2kit/packages/dispatch/substrate.py:_lift_principal_into_scope`:
  replace contextvar set with `set_request_principal`; replace the
  kwargs.setdefault dance with `child.seed_scoped(Principal, p)`.
  (Requires the child container in hand — verify call-site shape.)

## 4. Migrate dispatch stages to read via the bridge and seed explicitly

- [x] 4.1 `src/a2kit/packages/dispatch/stages.py:DispatchHookStage._wrapped`:
  open the child container explicitly (`container.child()`), call
  `current_request_principal()`, `child.seed_scoped(Principal, p)`
  when non-None, then enter `child.call_scope(...)`.
- [x] 4.2 `src/a2kit/packages/dispatch/stages.py:_run_authorize_gate`:
  same pattern — open child, read bridge, seed_scoped, open
  call_scope.
- [x] 4.3 Delete the `seed_principal_into_wire` import in stages.py.
- [x] 4.4 Delete `src/a2kit/packages/dispatch/_principal_scope.py`
  entirely (the fig leaf from `principal-single-source`).
- [x] 4.5 Delete the magic wire string `"_a2kit_principal"`
  everywhere (`grep -r '_a2kit_principal' src/a2kit/`).

## 5. Update `pre_hook` contract

- [x] 5.1 Add `SeedFn` Protocol in `packages/di/container.py` (or
  beside `Container` definition).
- [x] 5.2 Update `Container.call_scope` signature to thread a `seed`
  callable into the `pre_hook` invocation:
  `pre_hook(fn, wire_kwargs, seed)`.
- [x] 5.3 Migrate in-repo pre_hook consumers
  (`packages/connections/` — the connection-string resolution
  hook) to accept the third argument and call `seed(T, instance)`
  where they previously relied on the implicit walk.
- [x] 5.4 Document the new contract in
  `Container.call_scope`'s docstring with a code example.

## 6. Remove the implicit wire-by-type loop

- [x] 6.1 In `src/a2kit/packages/di/container.py:call_scope`, delete
  the `for _wire_val in wire.values(): ...` block (lines ~406-410).
- [x] 6.2 Add a unit test asserting that placing a typed value in
  `wire_kwargs` (without a matching parameter name on `fn`) does
  NOT create a SCOPED provider on the child.

## 7. Retire the L0 export (done in the same commit, no shim)

- [x] 7.1 Remove `_a2kit_request_principal` from
  `src/a2kit/packages/context/__init__.py:__all__`.
- [x] 7.2 Confirm `src/a2kit/packages/context/principal.py` is back
  to carrying only the `Principal` dataclass (the declaration was
  moved in task 2.2).
- [x] 7.3 Grep verification: `grep -rn '_a2kit_request_principal' src/`
  returns nothing.
- [x] 7.4 Grep verification: `grep -rn '_request_principal' src/`
  returns only `_principal_bridge.py`.

## 8. Drop the grep-based stage-source test

- [x] 8.1 Delete
  `tests/test_principal_single_source.py::test_dispatch_stages_source_has_no_principal_contextvar_read`
  — the structural import boundary supersedes it.
- [x] 8.2 Add a structural test: import `a2kit.packages.dispatch.stages`,
  walk its module-level imports, assert no
  `_request_principal` / `_a2kit_request_principal` symbol is reachable.

## 9. Test coverage

- [x] 9.1 DI provider override of `Principal` flows to the tool body
  (move from `tests/test_principal_single_source.py`, keep the test,
  update assertions to match new mechanism).
- [x] 9.2 No provider, no substrate publication → clear error (same).
- [x] 9.3 Substrate publication via `set_request_principal` flows to
  tool body (end-to-end through `DispatchHookStage`).
- [x] 9.4 `AuthorizeGateStage` resolves Principal via DI in the gate
  callable when a substrate has published.
- [x] 9.5 `tests/test_principal_propagation.py`: existing HTTP +
  MCP scenarios pass unchanged.
- [x] 9.6 `tests/packages/dispatch/test__principal_scope.py` (old):
  removed when the helper module is deleted.
- [x] 9.7 New `tests/packages/dispatch/test__principal_bridge.py`
  covers the named API.

## 10. Documentation + gates

- [x] 10.1 CHANGELOG entry under `Unreleased`:
  - "Breaking (internal API): `_a2kit_request_principal` removed
    from `a2kit.packages.context.__all__`; substrate adapters must
    import from `a2kit.packages.dispatch._principal_bridge`."
  - "Container.seed_scoped(type_, value) added; implicit wire-by-type
    loop in call_scope removed."
  - "pre_hook signature widens with a `seed` parameter."
- [x] 10.2 `make lint` clean.
- [x] 10.3 `openspec validate --changes --strict` passes for this
  change.
- [x] 10.4 Full pytest run green.
- [x] 10.5 Component map regenerated.
- [x] 10.6 ADR check: this change may affect ADR 0006 (DI semantics)
  and ADR 0019 (App/AppRuntime split). Sweep to confirm no ADR
  amendment needed; if so, file inline.
