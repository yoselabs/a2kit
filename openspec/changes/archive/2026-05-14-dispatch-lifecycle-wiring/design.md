# Design — dispatch-lifecycle-wiring

## Context

`v0.36` shipped the lazy + scoped DI primitives. The framework already
exposes `Container.dispatch(fn, wire_kwargs)` as the per-call dispatch
async-CM. What's missing is wiring it into the two production dispatch
sites (MCP transport, CLI runtime) so user tools see the new semantics
under the real wire. Until that lands, `per_call=True` and `Lazy[T]`
are dead-letter on production calls.

## Decisions

### D1 — Hook contract narrows to wire-side only

**Decision.** The dispatch hook's contract becomes: "given (fn,
wire_kwargs), return wire-side resolved kwargs". DI (provider chain
resolution, Lazy[T], cleanup recording) is framework job; the hook
does NOT call `apply_kwargs` or any DI method.

**Alternative considered.** Keep hook as "returns full kwargs (wire +
DI)" and have the wrapper only add per-call scope around fn invocation.
Rejected — the connections hook would still bypass `Container.get`'s
lifecycle path, so resources reached via a chain through a connection
config still wouldn't enter via `__aenter__`. Splitting the
responsibility forces all DI through one path.

**Reason.** One DI path. Hooks are wire-shape adapters; the framework
owns lifecycle.

### D2 — `Container.dispatch` accepts a `pre_hook`

**Decision.** Extend `Container.dispatch(fn, wire_kwargs, *, pre_hook=None)`.
When supplied, the pre_hook is awaited (or called sync) with
`(fn, wire_kwargs)` and its returned dict replaces `wire_kwargs` before
DI resolution. DI runs after — wire-resolved configs are visible to
the chain (the existing `pre_resolved` seed pattern).

**Alternative considered.** Compose in the caller (each wrapper opens
its own child, runs hook, then runs `resolve_params`). Rejected —
duplicates the composition across MCP + CLI + future transports.

### D3 — `identity_dispatch_hook` removed

**Decision.** Remove `a2kit.tool.identity_dispatch_hook`. The hookless
path is `await app._resolver.dispatch(fn, wire_kwargs)` (no `pre_hook`).
The CLI runtime's `dispatch_hook: Callable[..., Any] | None = None`
parameter becomes "if None, no pre_hook is composed".

**Reason.** A null-hook sentinel function carries no information the
framework can't derive from `None`. Removing it shrinks the surface.

### D4 — Connections hook simplifies

**Decision.** `make_connection_hook(stores)` returns a coroutine
`(fn, wire_kwargs) -> dict[str, Any]` that converts the `connection`
string into typed config instances and surfaces them as wire kwargs
(by tool-param name where applicable). It does NOT call
`container.apply_kwargs` — that's now the framework's responsibility.

**Migration.** Consumer-built custom hooks doing wire-side
preprocessing keep working; those calling `apply_kwargs` need to drop
the trailing line and let the framework's dispatch do DI.

### D5 — Exception preservation through the wrapper chain

**Decision.** The async-CM `dispatch` opens a `child` container that
runs as `async with` around the tool body. Tool exceptions propagate
naturally; per-call cleanups see `(exc_type, exc, tb)` via the
cleanup stack's forwarding (already implemented in v0.36).

The existing wire-error envelope wrapper (`_wrap_with_error_envelope`)
sits OUTSIDE the dispatch CM in the wrapper chain, so its catch-all
sees only the body exception that survives cleanup.

### D6 — Test coverage on real transport

**Decision.** New BDD scenarios driving `fastmcp.Client(transport=...)`
(via `TestClient`) and the CLI in-process invoker:

- `test_mcp_per_call_scope_unwinds_at_call_exit` — verify per-call
  resource cleanup runs after every MCP tool call.
- `test_mcp_lazy_param_skipped_under_real_wire` — Lazy[T] never
  invoked = resource never entered, across the MCP boundary.
- `test_cli_per_call_scope_unwinds` + `test_cli_lazy_param_skipped` —
  same for CLI.

These plug the gap between the §1 unit-level BDD baseline (direct
`app._resolver` API) and the production transports.

## Non-goals

- Async dispatch hook concurrency (single tool call = single child).
- Background work spawned by the tool body — explicitly out of
  per-call scope; user code that wants background tasks holds them
  outside the child container's lifetime.
- Removing the `Container.apply_kwargs` legacy API — kept as
  back-compat for the `a2kit.testing.client` internals and any other
  framework code that hasn't moved over yet. Mark for retirement in
  a follow-up.
