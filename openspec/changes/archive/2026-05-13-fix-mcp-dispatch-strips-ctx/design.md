# Design — fix-mcp-dispatch-strips-ctx

## Context

The bug is a wrapper-ordering correctness defect, not an API
redesign. The fix is small (≈10 lines of logic) and the design work
is mostly about pinning the invariant so the next reshuffle of the
wrapper chain can't re-introduce it.

Two design surfaces matter:

1. **Where in the wrapper chain does `ctx` re-enter the rewritten
   signature?** — D-WRAP-SHAPE.
2. **How is the call-time binding invariant pinned against future
   drift?** — D-INVARIANT and D-PARITY-MATRIX.

A third smaller decision: how to handle the `ctx: Context | None`
annotation form — D-OPTIONAL-CTX.

## D-WRAP-SHAPE — first shape, not second

The consumer feedback identifies two viable shapes:

- **Shape 1**: preserve `ctx` in the rewritten signature inside
  `_wrap_with_dispatch_hook`. FastMCP introspects, injects ctx
  into kwargs at call time, dispatch hook passes it through
  (container's `apply_kwargs` already does this — ctx is in fn's
  param list and falls into the wire-kwargs branch at
  `di/container.py:450-451`), body receives it.
- **Shape 2**: have the dispatch hook resolve ctx from FastMCP's
  Context object directly and inject it into `resolved` alongside
  container-resolved DI.

**Chosen: Shape 1.** Reasons:

- Shape 1 keeps a single source of truth for ctx binding: FastMCP
  injects it (the framework that owns the Context object's
  lifecycle), every consumer site reads from the same kwargs.
  Shape 2 introduces a second injection point inside the dispatch
  hook — now two places hold opinions about ctx, drift risk
  doubles.
- Shape 1 is a one-line change at the wrapper site (append a
  Parameter to `new_params`). Shape 2 requires the dispatch hook
  to import FastMCP types (or accept a Context probe via callback),
  breaking the transport-neutral design of `container_dispatch`.
- The "schema-clean" objection to Shape 1 — that ctx in the
  wire signature looks like an agent-facing input — does not
  apply. FastMCP introspects the function signature to decide
  which params *it* supplies (Context-typed params it owns) vs.
  which the *client* supplies (everything else). Ctx in the
  signature is the correct shape; it's why the requirement
  *"ctx parameter excluded from input schema"* (Scenario: ctx
  omitted from MCP schema) already passes — FastMCP's
  introspection naturally excludes Context-typed params from
  `inputSchema`. The bug was that we *over*-excluded.

## D-INVARIANT — assert at decoration time, not call time

The skeptic's strongest objection to a defensive guard in
`_wrap_with_ldd_state` is correct: it lives at the wrong layer
and can't reliably distinguish "framework dropped ctx" from
"ctx legitimately absent" (a future case for a tool that opts
out of LDD entirely).

The right guard fires at **decoration time**, inside
`_wrap_with_dispatch_hook` itself, after the rewrite:

```python
if ctx_param_name and ctx_param_name not in {p.name for p in new_params}:
    raise A2KitContextBindingBroken(
        fn_name=fn.__qualname__,
        ctx_param_name=ctx_param_name,
    )
```

Properties:
- Fires on App construction, before the App ever serves a request.
- False-positive impossible: if `meta.context_param_name` is set,
  the rewritten signature MUST contain that name for FastMCP to
  bind ctx correctly; this is invariant for all wrapper shapes,
  current and future.
- Failure-mode is correct: the next time someone reshuffles the
  wrapper chain (extracts a helper, reorders wrappers, factors
  out a new layer) and accidentally drops ctx from the rewrite,
  the App fails to build with a clear message — not silently in
  production months later.

The exception lives in `src/a2kit/exceptions.py` alongside
`AmbientContextMissing`:

```python
class A2KitContextBindingBroken(A2KitError, RuntimeError):
    """Raised at decoration time when the MCP wrapper chain's rewritten
    signature does not contain the tool's ctx parameter. This indicates
    a framework-internal regression in the wrapper-ordering invariant;
    user code cannot cause this. File an issue."""
```

## D-PARITY-MATRIX — fastmcp.Client in-memory, not subprocess

`fastmcp.Client(transport=build_mcp_server(app))` (already used in
`tests/test_field_logging_mcp_path.py`) drives the **real** wrapper
chain and the **real** Context binding code path. Subprocess stdio
JSON-RPC framing is below the tool dispatcher's concerns; the
v0.32 bug lives entirely above that boundary. In-memory client is
the right tool.

`testing.client._invoke_through_dispatcher` (`client.py:273`) is
NOT a substitute — it calls the hook on raw `fn`, then re-injects
`ctx` at line 292. The wrapper chain is never built, the rewritten
signature is never produced, the bug is structurally invisible.
This is by design (unit-test seam for tool bodies); it just means
the in-process test client cannot be the *only* MCP-side test.

### Test fixture shape

One App with four tools sharing one `app.singleton(State, ...)`:

```python
class State: tag = "S"

class R(Router):
    slug = "demo"
    @a2kit.read()
    async def tool_none(self, *, msg: str) -> dict:
        return {"msg": msg}
    @a2kit.read()
    async def tool_state(self, *, msg: str, state: State) -> dict:
        return {"msg": msg, "state_tag": state.tag}
    @a2kit.read()
    async def tool_ctx(self, *, msg: str, ctx: a2kit.ToolContext) -> dict:
        return {"msg": msg, "has_ctx": ctx is not None}
    @a2kit.read()
    async def tool_both(self, *, msg: str, state: State, ctx: a2kit.ToolContext) -> dict:
        return {"msg": msg, "state_tag": state.tag, "has_ctx": ctx is not None}
    tools = (tool_none, tool_state, tool_ctx, tool_both)
```

### The 9 cases

(8 from the original matrix + 1 explicit case for the
`ctx | None` rejection.)

| # | Case | Invariant guarded |
|---|---|---|
| 1 | `tool_none(msg="x")` parity | Sanity floor. |
| 2 | `tool_state(msg="x")` parity | Container injection identical both transports. |
| 3 | `tool_ctx(msg="x")` parity, `has_ctx=True` both | FastMCP Context binding identical to CLI `StderrToolContext`. |
| 4 | **`tool_both(msg="x")` parity, all fields** | **The v0.32 blocker.** |
| 5 | `tool_none(msg="x", extra="y")` raises `TypeError` both | Unknown-kwarg class parity. |
| 6 | `tool_state()` (missing msg) raises `TypeError` both | Missing-required parity. |
| 7 | `tool_ctx_emits_event()` ambient ctx non-None, event delivered both | `_wrap_with_ldd_state` ordering — guards round-8 §Related. |
| 8 | `tool_raises_user_error()` exception class preserved both | Round-8 P1 envelope regression (cross-cutting; once envelope ships, this asserts exact class; pre-envelope, asserts CLI class only). |
| 9 | App build with `ctx: ToolContext \| None = None` raises decoration-time error | D-OPTIONAL-CTX. |

Each case uses one helper:

```python
def assert_parity(name, kwargs, *, expected=None, expected_exc=None): ...
```

structural-equality on success; exact-exception-class on failure.

## D-OPTIONAL-CTX — reject at decoration time

The annotation form `ctx: ToolContext | None = None` (or
`Optional[ToolContext]`, or `Union[ToolContext, None]`) declares
typing that lies. The contract guarantees ctx is always bound when
declared:

| Transport | Bound to | Can be None? |
|---|---|---|
| MCP | live `fastmcp.Context` | No (FastMCP design) |
| CLI | `StderrToolContext()` synth at `cli/runtime.py:49` | No |
| Test client (post-rebuild) | real in-memory `fastmcp.Context` | No |

The Optional form enables defensive code (`if ctx is not None:
ctx.info(...)`) for a runtime path that doesn't exist, and creates
real ambiguity for our own wrapper code (skeptic's concern: should
the dispatch-hook wrapper preserve the `= None` default? Should it
expose ctx to FastMCP as required or optional?).

Reject the form at decoration time inside `find_context_param`.
Updated detection logic (`_is_tool_context`-aware):

```python
def find_context_param(fn):
    hints = resolve_hints(fn)
    for name, param in inspect.signature(fn).parameters.items():
        ann = hints.get(name, param.annotation)
        if _is_optional_tool_context(ann):
            raise A2KitInvalidContextAnnotation(
                fn_name=fn.__qualname__,
                param_name=name,
                hint="ctx is always bound by the dispatcher when declared; "
                     "drop `| None` from the annotation, or remove ctx "
                     "entirely if the tool does not need it.",
            )
        if _is_tool_context(ann):
            return name
    return None
```

`A2KitInvalidContextAnnotation` is a new exception class
(`exceptions.py`), sibling of `A2KitContextBindingBroken`. Fires
at `@a2kit.read()` decoration time via `tool.py:190` already
calling `find_context_param(fn)`.

### Search of existing codebase for the Optional form

Two hits in `src/a2kit`:
- `packages/testing/null_context.py:7` — documents the pattern in a
  prose docstring, not as a tool declaration. No code change needed.
- `packages/testing/client.py:216` — `_CapturingContext | None`
  inside the test-client's *own* internals (not a tool body). Not
  a `ctx: ToolContext` declaration; not affected by the rejection.

No production tool bodies use the Optional form. The migration
note in `proposal.md` covers any external consumer that did.

## Alternatives considered

### Alt-1: Keep ctx out of the rewritten signature; inject via dispatch-hook side channel

Shape 2 from the consumer feedback. Rejected above (D-WRAP-SHAPE).

### Alt-2: Make `_wrap_with_ldd_state` synthesize a fallback ctx when kwargs.get returns None

Hides the bug. The whole point of the silent-degrade was to be
tolerant of `ctx=None`; the cost was opacity. Doubling down on
synthesis would make the next regression even harder to localize.

### Alt-3: Keep Optional-ctx annotation form, document the runtime invariant

Tried in spirit by the current `_wrap_with_ldd_state` silent-degrade
behavior. Outcome: bugs slip past code review because the type lies
about runtime semantics. Rejected.

### Alt-4: Skip the decoration-time invariant assert; rely on the parity matrix

The parity matrix catches the *current* regression. The
decoration-time assert catches *future* regressions — every wrapper
chain change ever, not just this one. The assert is ~5 lines and
fires on every App build (zero CI configuration). The parity matrix
is necessary but not sufficient; the assert is the load-bearing
guard for the long run.

## Risks

- **Decoration-time exceptions during refactors.** Half-typed
  modules can raise on import (e.g. a contributor adds
  `@a2kit.read()` to a method with `ctx: ToolContext | None`
  pending a downstream rename). Acceptable — message points at
  the fix.
- **`A2KitContextBindingBroken` fires only on apps that combine
  the wrapper chain.** Apps with no container or no dispatch hook
  (`server.py:319` short-circuit) never reach the new code path.
  This is correct — those apps don't hit the bug either. But it
  means the invariant assert covers only the path where the bug
  exists, not the entire MCP-tool space. Documented in design,
  not a defect.
- **In-memory `fastmcp.Client` ≠ stdio JSON-RPC framing.** True;
  the env-gated subprocess smoke covers framing. The wrapper-chain
  bug is independent of framing.

## Out of scope

- The structured wire-error envelope (consumer feedback P1) — a
  separate change. Once it ships, parity-matrix case #8 tightens
  from "CLI class only" to "exact class both transports."
- `align-context-method-signatures` — separate in-flight change.
  This change adds one constraint (`ctx: ToolContext | None`
  rejection) that aligns with that change's spirit; if `align`
  ships first, this change inherits the cleaner state and the
  rejection still lands here.
- The decorator-completeness lint (wish #5), singleton teardown
  (wish #4), and `@a2kit.read(timeout=...)` (wish #2) — bundled
  into a future `dispatcher-polish` change.
