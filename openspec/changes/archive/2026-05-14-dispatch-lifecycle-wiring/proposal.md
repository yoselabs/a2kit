# dispatch-lifecycle-wiring

## Why

`v0.36 di-scoped-lifecycle` shipped the framework-side primitives
(`Container.dispatch`, `Container.child`, `Lazy[T]` recognition,
per-call cleanup stack) but the two production dispatch sites
(`mcp/server.py::_wrap_with_dispatch_hook` and
`cli/runtime.py::_invoke_tool_in_process`) still use the legacy
"hook returns kwargs, caller invokes fn" contract. Consequence: tools
declaring `per_call=True` resources or `Lazy[T]` parameters work via
direct `app._resolver.dispatch(...)` use but DO NOT flow through real
MCP / CLI invocations. The wave is half-shipped.

The connections package's hook also calls `Container.apply_kwargs`
(legacy resolution path), bypassing the new `Container.get` lifecycle
machinery for any tool routed through a connection.

## What Changes

- **BREAKING**: dispatch hook contract changes from "return kwargs"
  to "wire-side pre-resolution only" (no DI; no `apply_kwargs` calls).
  Existing hooks adapt by dropping the trailing `apply_kwargs` step.
- `_wrap_with_dispatch_hook` and `_invoke_tool_in_process` route
  through `app._resolver.dispatch(fn, wire_kwargs, pre_hook=hook)` —
  open a child container, run the wire-side pre-hook, layer DI
  resolution (Lazy[T]-aware) on top, run fn inside the child's
  lifetime, unwind cleanups on exit with exception preservation.
- `Container.dispatch` grows a `pre_hook` parameter so wire-side
  conversion (e.g. connection-string → typed config) is composed
  before DI.
- `connections/dispatch.py::make_connection_hook` is simplified to
  return only wire-side resolved kwargs (typed configs) without
  calling `apply_kwargs`.
- `identity_dispatch_hook` is removed — the hookless path uses
  `Container.dispatch(fn, wire_kwargs)` directly with no `pre_hook`.

## Impact

- Affected specs: `connections-dispatch-hook` (modified — contract
  narrowed; DI no longer in the hook's job), `request-scoped-di`
  (modified — production dispatch now honors per-call scope + Lazy[T]).
- Affected code: `src/a2kit/packages/mcp/server.py`,
  `src/a2kit/packages/cli/runtime.py`,
  `src/a2kit/packages/connections/dispatch.py`,
  `src/a2kit/packages/di/container.py`,
  `src/a2kit/tool.py` (removes `identity_dispatch_hook`),
  `src/a2kit/app.py` (`_default_dispatch_hook` simplified — no longer
  routes through `apply_kwargs`).
- Tests: new real-transport BDD coverage for per-call scope unwind +
  Lazy[T] under MCP and CLI; existing dispatch-hook tests adapt to
  the narrowed contract.
- Migration: consumer code that defined a custom `dispatch_hook`
  returning DI-resolved kwargs SHALL be split into a wire-side
  `pre_hook` plus the framework's standard DI resolution.
