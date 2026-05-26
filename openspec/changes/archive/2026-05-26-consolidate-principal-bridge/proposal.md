## Why

`principal-single-source` (archived 2026-05-26) made `stages.py` source
grep-clean of the substrate Principal contextvar by extracting reads
into a helper module — a fig leaf. The data path is unchanged:
Principal still threads through THREE storage layers (ContextVar →
magic-string wire kwarg → DI scope SCOPED provider) for ONE piece of
data, with the ContextVar declaration sitting publicly in L0
`packages/context.__all__`.

The audit identified two compounding problems:

1. **Contextvar in the wrong layer, semi-public.** `_a2kit_request_principal`
   lives in `packages/context/principal.py` (L0 bedrock) and is
   exported through `packages/context/__init__.py:__all__`. Anyone can
   reach it. The protection on `stages.py` is grep-based, not
   structural.

2. **Implicit DI registration via dict iteration.**
   `Container.call_scope` walks `wire_kwargs.values()` and registers
   each value's concrete type as a SCOPED provider. The wire-key
   string is meaningless; only `type(value)` matters. This is invisible
   at call sites (`kwargs.setdefault("_a2kit_principal", p)` is
   actually a DI registration). Two values of the same type collide
   silently. Subclass semantics undefined.

Spike findings (2026-05-26): FastMCP's `Context.set_state` and
ASGI/FastAPI `request.state` both work as substrate-native ambient
alternatives, but **neither is simpler than a stdlib ContextVar**.
They trade one bridge for two (substrate state + DI resolver), each
with framework-specific learning cost. The right move is to keep the
ContextVar as the *named, structural* bridge and remove the magic
stacked on top of it.

The principle this change locks in: **ContextVar for ambient
request-scoped data; DI for typed dependency resolution; one explicit
bridge between them, no implicit registration anywhere.**

## What Changes

- **BREAKING (internal API):** `_a2kit_request_principal` is removed
  from `packages/context/__init__.py:__all__` and the module-level
  declaration moves from `packages/context/principal.py` to a new
  private dispatch module `packages/dispatch/_principal_bridge.py`.
  No external consumer should be reading the raw ContextVar; this is
  internal scaffolding.
- New named writer API at the bridge:
  `set_request_principal(p) -> Token`,
  `reset_request_principal(token) -> None`. Substrate writers
  (`auth/api_key.py`, `mcp/principal_middleware.py`,
  `http/build.py`, `auth/testing.py`,
  `dispatch/substrate.py:_lift_principal_into_scope`) import these
  named entry points instead of the raw ContextVar.
- New `Container.seed_scoped(type_, value) -> None` method on the
  DI container — explicit public API for registering a per-call
  SCOPED instance on a child container.
- **BREAKING (internal API):** The implicit wire-by-type loop in
  `Container.call_scope` is removed. Any code that relied on the
  side-effect (publishing a typed instance into DI by placing it in
  `wire_kwargs.values()`) must now call `child.seed_scoped(type_,
  value)` explicitly. Wire kwargs return to their literal purpose:
  passing named values to `pre_hook` and to the function's own
  parameters.
- `pre_hook` contract widens: hooks receive a `seed: SeedFn` parameter
  they may call to publish typed instances, OR they accept the child
  container directly via a new signature. (Design.md decides.)
- `DispatchHookStage._wrapped` and `_run_authorize_gate` read
  Principal via `current_request_principal()` and seed via
  `child.seed_scoped(Principal, p)` — no kwargs-string magic.
- `_apply_authorize_gate` (HTTP path) stops scanning kwargs and
  stuffing the contextvar. Security guards already deliver Principal
  in `reserved_kwargs`; the gate seeds it on the new call_scope
  directly.
- **Deletes:** `packages/dispatch/_principal_scope.py` (the fig-leaf
  helper from `principal-single-source`), the magic string
  `"_a2kit_principal"` and all its hardcoded occurrences.
- `auth/testing.py:using_principal` migrates to use the named bridge
  API (`set_request_principal` / `reset_request_principal`) — the
  ContextVar still exists, just imported through a named, layered
  module.

## Capabilities

### New Capabilities

- `principal-bridge`: the named, private contextvar bridge that
  carries Principal from substrate auth boundaries to dispatch
  call_scope opening. Defines the writer API, the reader API,
  layer placement, and the "no public re-export" rule.

### Modified Capabilities

- `di-container-package`: adds `Container.seed_scoped(type_, value)`
  to the public surface; removes the implicit wire-by-type loop
  from `call_scope`.
- `di-per-call-scope`: documents the explicit seeding contract — a
  per-call SCOPED instance is registered via `seed_scoped`, never via
  a side effect of `wire_kwargs`.
- `principal-propagation`: updates the "single source of truth"
  requirement to name the bridge module as the *only* ambient
  source for Principal; substrate writers call the named API.
- `dispatch-pipeline`: the "stages MUST NOT read contextvar"
  requirement becomes structural (private module import boundary)
  instead of grep-based.

## Impact

- **Affected code:** `packages/context/principal.py` (declaration
  move), `packages/context/__init__.py` (remove from __all__),
  `packages/dispatch/_principal_bridge.py` (new),
  `packages/dispatch/_principal_scope.py` (delete),
  `packages/dispatch/stages.py` (use seed_scoped),
  `packages/dispatch/substrate.py` (use seed_scoped + named bridge
  API), `packages/di/container.py` (add seed_scoped, remove wire-by-type
  loop), `packages/auth/api_key.py`, `packages/auth/testing.py`,
  `packages/mcp/principal_middleware.py`, `packages/http/build.py`,
  any in-repo pre_hook consumer (the connection-resolution path in
  `packages/connections/`).
- **API surface:** no consumer-facing change. Tool authors still
  write `principal: Principal` and resolution works the same way.
  Internal substrate adapters update their import path.
- **Tests:** `auth/testing.py:using_principal` continues to work
  (re-implemented over the named bridge API). Any test directly
  importing `_a2kit_request_principal` from `packages/context` must
  update to import the named bridge API from
  `packages/dispatch/_principal_bridge`. Grep-based stage-source
  drift gate is retired in favor of the structural import boundary.
- **Dependencies:** none added; one stdlib `contextvars` use is
  consolidated.
- **Layer DAG:** `_principal_bridge.py` sits in dispatch (L4).
  Substrate adapters (L5: `auth`, `mcp`, `http`) import downward;
  stages (in `packages/dispatch/`, L4) import same-layer. No layer
  violations introduced.
- **Risk:** medium. The substrate writer migrations are mechanical
  (rename import, change function call). The DI container's
  wire-by-type removal touches every pre_hook user — design.md
  decides whether to keep a deprecated shim during migration or do
  a clean break (lean clean break: only in-repo pre_hooks exist).
- **Supersedes:** completes the work `principal-single-source`
  scoped but only fig-leafed.
