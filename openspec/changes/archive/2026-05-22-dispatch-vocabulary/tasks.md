## 1. Rename `Container.dispatch`

- [x] 1.1 Update the failing tests first — `tests/packages/di/test_dispatch_helper.py` (5 call sites) — to call `call_scope`.
- [x] 1.2 Rename the method `Container.dispatch` to `Container.call_scope` in `packages/di/container.py`; update its docstring.
- [x] 1.3 Update the framework call site in `packages/dispatch/stages.py` (`DispatchHookStage`).
- [x] 1.4 Confirm no `.dispatch(` reference to the container method remains under `src/` or `tests/`.

## 2. Rename the connections hook module

- [x] 2.1 Rename `packages/connections/dispatch.py` to `packages/connections/hook.py`; rename the function `install_connection_dispatch` to `install_connection_hook`.
- [x] 2.2 Update the `install_connection_hook` import — now in `packages/connections/install.py` (Change C moved it there from `__init__.py`); `install_connections` keeps its name and behaviour.
- [x] 2.3 Rename the mirror test file `test_dispatch.py` → `test_hook.py` (a 10-line mirror stub, not 6 call sites — the estimate predated the stub).

## 3. Verification

- [x] 3.1 Full test suite green (`make test`).
- [x] 3.2 `uv run a2kit lint static src/` clean — including the test-layout mirror rule for the renamed connections module.
- [x] 3.3 `grep -rn "\.dispatch(" src/ tests/` shows no hit referring to the former container method or the connections function.
- [x] 3.4 `openspec validate --changes --strict` passes; the change is archive-ready.
