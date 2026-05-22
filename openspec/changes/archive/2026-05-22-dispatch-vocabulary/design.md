## Context

"dispatch" is overloaded across three layers. The pipeline package owns the word legitimately. `Container.dispatch()` and `connections/dispatch.py` borrow it and collide. Investigation during the explore session confirmed both borrowed uses are internal: `Container.dispatch` has 6 call sites (5 tests, 1 framework seam in `dispatch/stages.py`) and is not exported; `install_connection_dispatch` is not in the connections `__all__` — `install_connections` is the public entry point. So both can be renamed outright with no compatibility surface.

## Goals / Non-Goals

**Goals:**

- One referent per name. The pipeline keeps "dispatch"; the other two get names that say what they do.
- No consumer-facing change.

**Non-Goals:**

- Renaming `packages/dispatch`.
- Renaming the "dispatch hook" concept or the `connections-dispatch-hook` capability — "dispatch hook" is unambiguous.
- Any behaviour change. Pure rename.

## Decisions

**1. `Container.dispatch` becomes `Container.call_scope`.**
The method is an `@asynccontextmanager` that opens a per-call child container, runs the optional pre-hook, resolves DI kwargs, yields the merged kwargs, and unwinds the child on exit. It is the per-call DI *scope*. `call_scope` reads correctly at the call site: `async with container.call_scope(fn, wire) as kwargs:`.
Alternatives considered: `scope_call` (rejected — noun/verb order reads worse as a CM), `resolve_and_enter` (rejected — describes the steps, not the concept), `dispatch_scoped` (rejected — keeps the colliding word).

**2. `connections/dispatch.py` becomes `connections/hook.py`; `install_connection_dispatch` becomes `install_connection_hook`.**
The file already contains `make_connection_hook` — the module's concept is the connection hook. `hook.py` names that concept and clears the collision with `packages/dispatch`. The function rename follows the module.

**3. No compatibility aliases.**
Both surfaces are internal (verified). Per AGENTS.md's no-backward-compat-shims principle, the old names are removed; any stale reference fails loudly at import or attribute access. A `Container.__getattr__` migration-hint stub is unnecessary because there is no external caller to guide — the rename lands entirely within `src/` and `tests/` in one change.

## Risks / Trade-offs

- **A missed call site fails loudly, not silently** → that is the intended outcome of the no-shim policy; a leftover `.dispatch(` raises `AttributeError`. Mitigation: the investigation already enumerated all 6 + 8 call sites; the tasks update each explicitly.
- **Shared capability spec ordering** → `dispatch-vocabulary` modifies `di-container-package` and `connections-dispatch-hook`; no other queued change touches those specs, so there is no wave-ordering constraint.
