# Spike — FastMCP CodeMode over a2kit connection-scoped DI

Status: complete, passed. Feeds the code-execution surface in
[`VISION.md`](VISION.md). Not a contract — a de-risking experiment.

## Question

FastMCP 3.2 ships `experimental.transforms.CodeMode`: it collapses the
tool catalog into `search` / `get_schema` / `execute`, and runs
agent-authored Python in a Monty sandbox where the only callable is
`call_tool(name, params)`. That bridge calls
`ctx.fastmcp.call_tool(...)` under the hood.

a2kit tools are not plain functions. Each is wrapped by
`_wrap_with_dispatch_hook` (`packages/mcp/server.py`) so that, **per
call**, the connections dispatch hook resolves the wire
`connection: str` into a typed config and the DI container resolves
request-scoped dependencies (`store: TrackerStore`).

So the unknown was narrow: **when sandboxed code calls
`call_tool("<a2kit tool>", {"connection": "default", ...})`, does the
nested `ctx.fastmcp.call_tool` re-run a2kit's per-call dispatch hook
and DI — or is connection/DI scope lost?** This was named in
`VISION.md` as "the one genuinely unproven piece" of the
code-execution surface.

## Method

Harness: `scripts/spike_code_exec_di.py`. It drives the unmodified
`examples/tracker` app — the canonical connection + per-call-DI
example — through the real FastMCP in-memory client:

1. Seed a `TrackerConn` connection record and a tracker DB with two
   tasks.
2. `build_mcp_server(app)` — no a2kit changes.
3. `server.add_transform(CodeMode())` — stock FastMCP, default
   `MontySandboxProvider`.
4. Drive `search` / `execute` over `fastmcp.Client(server)` and
   assert on connection-scoped, DI-wired tool behaviour.

## Findings

1. **Catalog collapse works, zero a2kit changes.** After
   `add_transform(CodeMode())` the surface is exactly `execute`,
   `get_schema`, `search`. a2kit's nine tracker tools route through
   discovery.

2. **The discovery schema exposes `connection`.** `search` with
   `detail="full"` shows the `connection` wire param on a2kit tools.
   a2kit's rewritten wrapper signature (which synthesises
   `connection: str`) survives CodeMode's schema projection — so an
   agent learns it must pass `connection`.

3. **Core result — connection scope and per-call DI flow through the
   nested call.** Sandboxed code
   `await call_tool("list_tasks", {"connection": "default"})`
   succeeded: the nested `ctx.fastmcp.call_tool` re-ran
   `_wrap_with_dispatch_hook`, the connections hook resolved
   `connection="default"` to a typed `TrackerConn`, DI injected
   `TrackerStore` built from that connection, and the tool returned
   the seeded tasks. **The unproven piece is proven — it works out of
   the box.**

4. **The sandbox receives structured data, not formatted text.** The
   sandbox got `{'result': [{'id': 't1', 'title': 'First task',
   'done': False, 'assignee': None}, ...]}` — a real Python
   dict/list, because `_unwrap_tool_result` picked up the tool's
   `structured_content`. Agent code can index and filter directly; no
   TSV/JSON string parsing inside the sandbox. This is a genuine
   ergonomics win for the code-execution surface.

5. **a2kit middleware fires on the nested path.** The list result
   carried only the four `@a2kit.list_` default fields (`id`,
   `title`, `done`, `assignee`) — `project_id` was projected out.
   `ListViewMiddleware` ran on the sandbox-driven call, so a2kit's
   list-view semantics hold through code mode.

6. **The failure mode is legible.** `call_tool("list_tasks", {})`
   (no connection) surfaced
   `ValueError: 1 validation error ... connection — Missing required
   keyword only argument`, raised as `MontyRuntimeError` and wrapped
   as `ToolError`. An agent gets a clear, self-correctable message.

7. **Monty ran the async code.** `pydantic-monty` executed
   `await call_tool(...)` plus a top-level `return`. Installed
   version was `0.0.17`; `fastmcp[code-mode]` pins `0.0.11` — the
   `Monty(code).run_async(...)` API was stable across both.

## Verdict

**Code execution over a2kit connection-scoped, DI-wired tools works
with `build_mcp_server(app)` + `server.add_transform(CodeMode())` and
zero a2kit framework changes.** The highest-risk item in the vision is
no longer a feasibility risk — it is now an integration-and-packaging
task.

## Implications for the vision / OpenSpec

- **Adopt FastMCP `CodeMode` wholesale** (`VISION.md` principle 7).
  Do not build a sandbox or a tool-callback bridge — they exist and
  work.
- The code-execution OpenSpec change is **not** "make code execution
  feasible." It is: pick the author-facing toggle, gate capabilities,
  package the dependency, decide discovery-tool defaults.

What remains genuine OpenSpec scope (not spike risk):

- **Capability gating — the real a2kit value-add.** Stock `CodeMode`
  exposes *every* tool to the sandbox indiscriminately. a2kit's
  `destructive` / `visibility` / `open_world` semantic flags
  (`VISION.md` principle 5) are not consulted. Gating destructive
  tools behind an explicit grant is unbuilt and is the thing a2kit
  adds on top of FastMCP.
- **Packaging.** `pydantic-monty` must become a proper optional
  dependency confined to a lazily-imported `a2kit.packages.*` module
  (`VISION.md` principle 6). It is currently an ad-hoc `uv pip
  install` and is **not** in `pyproject.toml` / `uv.lock`.
- **Experimental-namespace churn.** `CodeMode` lives in FastMCP's
  `experimental` namespace; adopting it accepts API drift until it
  graduates. Watch against the `fastmcp<4` pin.
- **`connection` ergonomics in code mode.** The agent must repeat
  `connection` in every `call_tool`. Acceptable, but a sandbox-level
  default connection is worth a design thought.
- **Discovery tools.** Defaults are `search` (BM25) + `get_schema`.
  Whether a2kit customises the discovery set is an OpenSpec choice.

## Residual risks / not covered

- Only a `@a2kit.list_` tool was exercised end to end.
  `_wrap_with_dispatch_hook` is verb-agnostic, so `@read` / `@write`
  should behave identically — but this was not run empirically.
- No authentication in the loop. `CodeMode` behind a remote
  OAuth-protected MCP server is untested.
- Monty `ResourceLimits` (duration / memory / recursion caps) were
  not exercised.

## Reproduce

```bash
uv pip install pydantic-monty
uv run python scripts/spike_code_exec_di.py
```
