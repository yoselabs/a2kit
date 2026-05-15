## Why

a2web's v0.38 friction inventory (`A2KIT_FEEDBACK_v0.38.md`,
Friction B) raised a real ergonomic pain: every tool in a
router-driven app declares `ctx: a2kit.ToolContext` in its signature,
then `del ctx` in the body because the tool itself never uses it.
The param exists only to flip the dispatcher into "bind ambient
ctx" mode so downstream `a2kit.ldd.*` primitives don't crash with
`AmbientContextMissing`.

a2web has one router with seven tools; that's seven `ctx` params and
seven `del ctx` lines for zero semantic content in the body.

### a2web's proposal — and why we're not taking it

a2web asked for **unconditional ambient binding** on every
framework-dispatched tool, dropping the `ctx: ToolContext`
requirement from the signature entirely.

We're declining for three reasons:

1. **The signature is a contract for the reader, not just a flag
   for the dispatcher.** A `ctx` param signals "this tool
   participates in the ambient dispatch lifecycle." Removing it
   makes LDD emissions four calls deep into spooky action — exactly
   the implicit-magic the framework has been pruning since v0.31.

2. **v0.36 introduced standalone DI resolution outside a tool
   call.** Unconditional bind splits the model: dispatched-tool
   gets ambient, standalone doesn't. The current rule is uniform —
   `ctx in signature ⇒ ambient binds`.

3. **The `del ctx` smell is a body-level convention problem; it
   shouldn't drive a signature-contract change.** Renaming to
   `_ctx` or letting the linter accept it as intentionally-unused
   are body-level fixes.

### Counter-proposal — Router-level marker

Promote a2web's own fallback ask to the primary fix: add a
class-level `emits_ldd: bool = False` marker on `Router`.
Routers that opt in get ambient state bound automatically for
every tool they own — no per-tool `ctx` declaration needed.

```python
class WebRouter(a2kit.Router):
    slug = "web"
    emits_ldd = True            # ← opt-in
    tools = (fetch, scrape, ...)
```

The dispatcher reads `emits_ldd` at registration. When True, every
tool from that router runs inside `ldd_state_for_call(...)` even
if its signature has no `ctx` param. Tools that genuinely need ctx
in the body (e.g. `await ctx.report(...)`) can still declare it
and the dispatcher injects it via the existing path.

For a2web specifically: **one router, one line, every tool fixed,
no `del ctx` anywhere.**

## What Changes

### Spec — `router-conventions` capability

- ADD requirement: `Router.emits_ldd: ClassVar[bool] = False`. When
  True, every tool dispatched through that router runs inside an
  active LDD ambient (`ldd_state_for_call(ctx=<dispatch ctx>,
  events_enabled=True, reports_enabled=True)`) regardless of
  whether the tool signature declares `ctx`.
- ADD requirement: tools on `emits_ldd=True` routers MAY omit the
  `ctx: ToolContext` param. When omitted, the dispatcher SHALL NOT
  inject ctx into the tool kwargs. When declared, the dispatcher
  SHALL inject it as today.
- ADD requirement: routers on `emits_ldd=False` (the default)
  behave exactly as today — tools requiring ambient must declare
  `ctx`.

### Code — dispatcher path

- `Router` base class: add `emits_ldd: ClassVar[bool] = False`
  attribute with docstring.
- Dispatcher: at tool-registration time, record whether the owning
  router has `emits_ldd=True`. When dispatching, wrap the tool
  invocation in `ldd_state_for_call` if either (a) the router has
  the marker OR (b) the tool signature declares `ctx` (today's
  behavior). This preserves the uniform rule "ambient binds iff
  the framework can prove the tool wants it."
- Lint: A2K rule that flags `del ctx` immediately after a tool
  body opens, suggesting the consumer drop the param if the
  router has `emits_ldd=True`. Advisory only — does not fail
  build by default.

### Out of scope

- **Unconditional binding for all dispatched tools.** Rejected
  per Why §1-3.
- **Auto-detecting LDD usage in the tool's call graph.** Not
  statically feasible.
- **Per-tool `@a2kit.uses_ldd` decorator.** Same ceremony cost as
  declaring `ctx`. The Router-level marker is the cheaper opt-in.
- **Standalone DI ambient.** Out of scope for this change — the
  marker only affects the dispatch path.

## Impact

- **Migration cost for consumers** — zero. Default is `False`;
  existing routers behave identically. Consumers wanting the
  ergonomics flip one class attribute.
- **a2kit surface** — one new `ClassVar` on `Router`. No new
  top-level symbols.
- **Test coverage** — needs new tests for the dispatcher path:
  ambient binds when marker set + no ctx param; ambient still
  binds when marker set + ctx param declared; no ambient when
  marker unset + no ctx param (today's behavior preserved).

## Alternatives considered (briefly — see design.md for full)

- A1: Unconditional bind — a2web's primary ask. Rejected.
- A2: Auto-detect via static analysis. Rejected (call graph
  through indirection is not statically traceable).
- A3: Per-tool `@uses_ldd` decorator. Same ceremony, lower
  value. Rejected.
- A4: Move ctx-binding decision to a separate `App.ldd_default`
  setting. Too coarse — apps with mixed-LDD-emission routers
  can't express it.
