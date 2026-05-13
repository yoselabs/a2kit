# Fix MCP dispatch stripping `ctx` from the wrapped tool signature

## Why

Any tool that declares **both** a container-resolved param (`state: T` via
`app.singleton(T, ...)`) AND `ctx: a2kit.ToolContext` works over CLI and
fails 100% of the time over MCP with `TypeError: <fn>() missing 1
required keyword-only argument: 'ctx'`. The wire reports only the
masked string `"Error calling tool '<name>'"` — no class, no message,
no traceback — leaving consumers with no signal that the call shape
is the cause.

The bug shipped in v0.32 and slipped past release validation because
the in-process test client (`a2kit.testing.client`) bypasses the
production wrapper chain entirely (`packages/testing/client.py:273`
calls the dispatch hook on the raw `fn`, then re-injects `ctx` at
line 292). Every "MCP test" in `tests/` either uses this in-process
client or doesn't combine `state` + `ctx`. The only test that drives
a real `fastmcp.Client(transport=build_mcp_server(app))`
(`tests/test_field_logging_mcp_path.py`) doesn't combine the two
declarations either.

Production impact, downstream: a2web v0.6.0 ships with full MCP
outage (`mcp__a2web__fetch` errors on 100% of calls); CLI works
unchanged.

### Root cause

`packages/mcp/server.py:316-328` assembles the wrapper chain
`fn → router_enrichers → dispatch_hook → ldd_state`. The
dispatch-hook wrapper rewrites `__signature__` to expose only wire
params, sourced from `wire_input_params` in `signature.py:86`.
That helper composes `user_input_params` (which strips `ctx` by
name at line 80-82) and a container-injectable filter
(line 107-109). The rewritten signature contains *only* the
agent-facing wire params — never `ctx`. FastMCP introspects the
outermost wrapper, follows the `functools.wraps` `__wrapped__`
chain, lands on the dispatch-hook wrapper's explicit
`__signature__`, sees only the wire params, and never injects
`ctx` into kwargs at call time. Inside the wrapper chain
`_wrap_with_ldd_state` reads `kwargs.get(ctx_param_name)` → `None`
and silently sets the ambient LDD state with `ctx=None`; the
dispatch hook resolves the container DI; the original `fn` is
called missing its required `ctx` kwarg → TypeError.

`packages/cli/builder.py` does not hit this because its call path
binds `state` and `ctx` directly to the underlying `fn` without
rebuilding a FastMCP-shaped signature for schema introspection.

### Why the existing requirement is insufficient

`mcp-context-passthrough` requires that `ctx` be **excluded from
the user-facing input surface** (Requirement: *ctx parameter
excluded from input schema*). The implementation honors this for
the wire `inputSchema`, but overreaches and also drops `ctx` from
the *internal* signature FastMCP uses for call-time argument
binding. The two are different surfaces; the requirement was read
as covering both.

## What Changes

- `_wrap_with_dispatch_hook` re-appends the original `ctx`
  `inspect.Parameter` to the rewritten signature when
  `meta.context_param_name` is set, sourced from the canonical
  `find_context_param` result already cached on `A2KitMeta`. FastMCP
  then introspects a signature shaped `(wire_params..., ctx)`,
  injects ctx at call time, container's `apply_kwargs`
  (`di/container.py:425-460`) passes ctx through (wire_kwargs
  branch — ctx is in fn's param list), and the body receives all
  expected kwargs.

- `_wrap_with_dispatch_hook` raises `A2KitContextBindingBroken`
  (new, in `exceptions.py`) at **decoration time** when
  `meta.context_param_name` is set but the rewritten signature
  does not contain that parameter name. This is a framework-internal
  invariant — fires the moment a future wrapper reshuffle drops
  ctx from the rewritten signature, before the App ever serves
  a request.

- `find_context_param` (canonical resolver, `signature.py:62`)
  rejects `ctx: Context | None` and `ctx: Optional[Context]`
  annotation forms at decoration time with a clear message
  pointing at the contract — `ctx` is always bound by the
  dispatcher when declared; the Optional shape is misleading
  typing with no runtime path that produces `None`.

- New test file `tests/test_transport_parity.py` exercises a
  transport-parity matrix using
  `fastmcp.Client(transport=build_mcp_server(app))` for the MCP
  leg (existing pattern from
  `tests/test_field_logging_mcp_path.py`) and
  `cli.runtime.invoke_tool_sync` for the CLI leg. One App fixture,
  four declaration combos (none / state-only / ctx-only / both),
  asserts structural-equal payloads and exact-class exception
  parity. The "both" case is the v0.32 blocker regression test.

- One env-gated stdio smoke test
  (`tests/test_transport_parity_stdio.py`, opt-in via
  `A2KIT_SLOW_TESTS=1`) covers JSON-RPC framing as a canary; not
  part of default CI.

- `OPERATIONAL_CONTRACTS.md` adds Q-Ctx ("Context binding
  invariants") cross-linking the new test file and the new
  `A2KitContextBindingBroken` diagnostic.

## Impact

- **Affected specs**: `mcp-context-passthrough` — adds a new
  scenario under *ctx parameter excluded from input schema*
  pinning that exclusion applies to the user-facing wire schema
  only, and adds two new requirements covering call-time binding
  and the Optional-ctx rejection.
- **Affected code**:
  - `src/a2kit/packages/mcp/server.py` — `_wrap_with_dispatch_hook`
    accepts `ctx_param_name` arg; appends ctx Parameter; raises
    on invariant break.
  - `src/a2kit/signature.py` — `find_context_param` rejects
    Optional-ctx forms.
  - `src/a2kit/exceptions.py` — new
    `A2KitContextBindingBroken(A2KitError, RuntimeError)`.
  - `OPERATIONAL_CONTRACTS.md` — new Q-Ctx section.
  - `tests/test_transport_parity.py` — new file.
  - `tests/test_transport_parity_stdio.py` — new file (opt-in).
- **APIs**: BREAKING for any consumer that declared
  `ctx: ToolContext | None = None`. Migration is
  `s/ctx: ToolContext \| None( = None)?/ctx: ToolContext/`. No
  consumers outside this repo are known to use the Optional form;
  if any exist they were relying on a runtime invariant that
  never produced `None`.
- **Dependencies**: none.
- **CI cost**: `tests/test_transport_parity.py` adds 8 in-memory
  FastMCP sessions; negligible (≈ existing
  `test_field_logging_mcp_path.py` × 4). Subprocess stdio smoke
  is env-gated and not in default CI.
- **Risk**:
  - The Optional-ctx rejection at decoration time is a hard error.
    Mitigated by the migration being mechanical and the prior
    runtime invariant being unchanged (no caller ever received
    `None`).
  - `A2KitContextBindingBroken` fires at decoration time, so a
    half-typed module during refactor *could* raise on import.
    Acceptable — the invariant should hold at all times; firing
    early is the point.
- **Out of scope**: the FastMCP wire-error envelope (P1 in the
  consumer feedback) is a separate change
  (`mcp-structured-wire-error-envelope`); see that proposal for
  the structured `{class, message, [traceback]}` payload that
  would make the bug self-diagnosing on the wire.
