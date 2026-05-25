## Context

The recent Surface Protocol wave made the registry the source of truth
for mounted substrate adapters. `SURFACE_REGISTRY.names()` returns the
list. Decorator validation in `_verbs.py` still hardcodes the surface
set, which means adding a transport edits both the new Surface and
`_verbs.py` — a coupling the registry was supposed to eliminate.

The complication: `_verbs.py` lives in core sub-unit `authoring` (L2);
`SURFACE_REGISTRY` lives in `a2kit.packages.dispatch.surface` (L4).
Reading the registry from `_verbs.py` is an upward edge — `A2K-LAYER`
would (correctly) reject it.

## Goals / Non-Goals

**Goals:**
- Verbs validate `expose=` against the live registry.
- Adding a transport requires zero edits to authoring-layer code.
- Layer-DAG remains green (`A2K-LAYER` and `A2K-PKG-FRONT-DOOR` both
  pass).
- Error messages name the currently-registered surfaces, not a stale
  literal.

**Non-Goals:**
- Restructuring `SURFACE_REGISTRY` itself (the contract is already
  good).
- Moving Surface metadata (`reserved_types`, `substrate_dep_markers`)
  to L0; only the *names* need to be visible to L2.
- Pluggable verb decorators for third-party transports (the verb
  family is locked per ADR 0003).

## Decisions

### 1. Where the surface name set lives — kernel-layer leaf module

Introduce `src/a2kit/_surface_names.py` (or similarly named module
under the `kernel` core sub-unit, L1). It defines:

```python
_REGISTERED_SURFACE_NAMES: list[str] = []

def register_surface_name(name: str) -> None: ...
def registered_surface_names() -> tuple[str, ...]: ...
```

This is the layer-clean home: L1 leaves can be imported by L2
(authoring) and L4 (dispatch).

`SURFACE_REGISTRY.register_surface()` calls `register_surface_name()`
as a side-effect to keep the two in lockstep. The kernel module is the
*names* source-of-truth; the dispatch registry remains the *instances*
source-of-truth for everything else.

Alternative A considered: make `_verbs.py` reach into
`a2kit.packages.dispatch.surface` via lazy import inside the function
body. Rejected — defeats `A2K-LAYER` (and the lint rule already catches
`TYPE_CHECKING` imports, so even a lazy ref is detectable).

Alternative B considered: move `SURFACE_REGISTRY` itself down to L1.
Rejected — `SURFACE_REGISTRY` carries `Surface` instances with
`reserved_types` (which reference `Principal`, etc.), and pulling that
graph into L1 contaminates the kernel.

Alternative C considered: pass the allowed-names set into the decorator
factory at finisher time. Rejected — decorators are import-time
constructs in tool authoring; a finisher-time injection would change
the authoring ergonomics.

### 2. Self-registration order

The bundled `McpSurface` and `ApiSurface` already self-register at
lazy front-door load (per `surface-protocol` spec). The
`register_surface_name()` call happens inside `register_surface()`, so
the names list is populated by the same import. By the time a verb
decorator runs in user code (which presumably imports `a2kit.mcp` or
`a2kit.api` or similar to expose a surface), the names list is
non-empty.

For verbs decorated *before* any surface is imported, the names list
is empty. Validation then fails loudly: "no surfaces registered;
import `a2kit.packages.mcp` or `a2kit.packages.http` to mount one."
This is correct — `expose=("mcp",)` with no MCP surface mounted is a
real bug we'd want to catch.

### 3. Error message shape

```
expose=('foo',) is not valid. Registered surfaces: ('mcp', 'api').
A surface name is registered when its package is imported
(e.g. `import a2kit.packages.mcp`). To extend, implement the Surface
Protocol and call register_surface(...).
```

The message enumerates from the live registry, not from a literal.

### 4. Test surface

Tests register a synthetic third surface (`StubSurface("test")`) and
verify:
- `@a2kit.read(expose=("test",))` does not raise.
- The error message for an unknown name lists `mcp`, `api`, `test`.
- After unregistration cleanup (test fixture), the decorator behaviour
  returns to baseline.

## Risks / Trade-offs

- **[Risk] Import-order subtlety: a user expose-ing a surface that
  isn't imported yet** → Mitigation: the validation already fails;
  the new message tells them exactly what to do. This is strictly
  better than the previous behaviour (which silently allowed
  `expose=("mcp",)` even when MCP wasn't mounted).
- **[Risk] The L1 leaf module is a new place to know about** →
  Mitigation: it's a 30-line file with two functions; documented in
  the layer manifest comments.
- **[Risk] Layer manifest needs updating to acknowledge the new
  module** → Mitigation: covered in tasks; `_KERNEL_MODULES`
  frozenset in `layers.py` adds the new module name.
- **[Trade-off] Two places now know about the surface name list (L1
  leaf + L4 registry)** → Accepted: they are mechanically synced by the
  registry's `register_surface` calling into the leaf; no consumer
  needs both.

## Migration Plan

1. Create `src/a2kit/_surface_names.py` with the empty list + two
   functions.
2. Add it to `_KERNEL_MODULES` in `layers.py`.
3. Wire `SURFACE_REGISTRY.register_surface` to call
   `register_surface_name` as a side-effect.
4. Replace `_verbs.py:111` literal with `registered_surface_names()`.
5. Update error message in `_verbs.py` to enumerate from the live
   names.
6. Add tests covering: register-and-allow, unknown-name error message,
   empty-registry error message.

Rollback: revert the four edits; the literal is small and isolated.

## Open Questions

- Should the L1 leaf module live at `src/a2kit/_surface_names.py` (a
  private top-level kernel module) or at
  `src/a2kit/packages/_kernel/surface_names.py` (a packages-level
  kernel)? Leaning the former — it's a top-level concern, only ~30
  lines, and the `_` prefix marks it private. Decide during
  implementation; either is layer-clean.
