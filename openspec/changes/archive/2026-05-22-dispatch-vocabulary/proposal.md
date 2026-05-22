## Why

The word "dispatch" names three unrelated things in a2kit:

- `packages/dispatch` — the Stage pipeline (timeout, enricher, error-capture).
- `Container.dispatch()` — a DI-resolution async context manager that opens a per-call scope and yields resolved kwargs.
- `connections/dispatch.py` plus `install_connection_dispatch()` — connection-hook wiring.

A reader who hits "dispatch" cannot tell which is meant — and they call each other (`DispatchHookStage` invokes `Container.dispatch`). AGENTS.md principle 2 forbids "multiple ways of doing the same thing"; this is its vocabulary cousin: one word, three referents, no way to disambiguate at a glance.

## What Changes

- `packages/dispatch` keeps the name — it is the canonical owner of "dispatch" (it *is* the dispatch pipeline).
- **BREAKING (internal):** rename `Container.dispatch(fn, wire_kwargs, *, pre_hook=None)` to `Container.call_scope(...)`. The method opens a per-call DI scope and yields resolved kwargs; `call_scope` names what it does. It is accessed only as `app._resolver.call_scope` in framework code (6 call sites, no consumer-facing exposure), so no compatibility alias is required — the old name is simply gone.
- **BREAKING (internal):** rename the module `connections/dispatch.py` to `connections/hook.py` and the function `install_connection_dispatch()` to `install_connection_hook()`. Both are internal to the connections package; `install_connections()` remains the public entry point and is unchanged.

The "dispatch hook" concept itself (the `pre_hook` seam in the pipeline, the `connections-dispatch-hook` capability) is *not* renamed — "dispatch hook" is a legitimate, unambiguous term for the hook stage in the dispatch pipeline.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `di-container-package`: the container's public surface lists `dispatch(...)`; renamed to `call_scope(...)`.
- `connections-dispatch-hook`: the requirement text references `Container.dispatch`; updated to `Container.call_scope`.

## Impact

- **Code:** `packages/di/container.py` + `packages/di/resolver.py` (method rename on the `Container` class and the `Resolver` Protocol), `packages/connections/dispatch.py` → `hook.py` (module + function rename), `packages/connections/install.py` (the `install_connection_hook` import — Change C moved it here from `__init__.py`), `packages/dispatch/stages.py` (the `DispatchHookStage` call site), `packages/di/__init__.py` (docstring).
- **Tests:** `tests/packages/di/test_dispatch_helper.py` (5 call sites), `tests/packages/di/test_container.py` + `test_resolver_protocol.py` (surface-name assertions), `tests/packages/connections/test_dispatch.py` → `test_hook.py` (mirror-stub rename).
- **Specs:** the `di-container-package` and `connections-dispatch-hook` deltas carry the requirement changes; `openspec/specs/request-scoped-di/spec.md` also cited `Container.dispatch` (6 places, incl. a requirement title) and is reconciled directly — a rename-citation hygiene edit, not a requirement change.
- **Public API / consumers:** unchanged. `install_connections()` keeps its name; `Container.call_scope` and `install_connection_hook` are internal.
- **No compatibility shims:** both renamed surfaces are internal and have no external callers, so per AGENTS.md the old names are removed outright rather than aliased.
