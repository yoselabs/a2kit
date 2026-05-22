# a2kit Vision — write the tool, get every surface

> Status: north-star vision. Not a contract. Capability specs under
> `openspec/specs/` and ADRs under `docs/adr/` are where this vision
> turns into committed behaviour. This file exists to give every
> OpenSpec change a shared destination to point at.

## The thesis

An author writes a tool **once** — a decorated function with typed
parameters and a typed return. a2kit makes that one function
reachable from every surface a human or an agent could want, with
**zero per-surface code** and **zero required configuration**.

The author never imports a transport. Never hand-writes a CLI
parser. Never maintains an OpenAPI schema. Never thinks about how
code-execution sandboxing works. They write the function body. The
framework owns everything between that function and the wire.

This is the whole product in one sentence:

> **No tool author should ever care which surface their tool is
> consumed through. Every surface is bundled, abstracted away, and
> just works out of the box.**

Everything below is in service of that sentence.

## Why this is the right bet (the 2026 context)

The agentic-tooling ecosystem converged, in the last six months, on
exactly the shape a2kit's protocol-agnostic core was built for:

- **MCP became a neutral standard.** Anthropic donated the Model
  Context Protocol to the Linux Foundation's Agentic AI Foundation
  (with Block, OpenAI, Google, Microsoft, AWS, Cloudflare,
  Bloomberg). Betting on MCP is no longer betting on one vendor.
- **"One definition, many generated surfaces" is the blessed
  direction.** Anthropic acquired Stainless, whose entire product is
  generating SDKs and MCP servers from a single API definition.
- **Code execution with MCP is the new efficiency frontier.**
  Presenting tools as code on a filesystem and letting the agent
  read only what it needs cut one reference workflow from ~150,000
  tokens to ~2,000 — a 98.7% reduction.

a2kit was early to the core idea. The vision is to finish the job:
make *every* surface free, including the two new ones the ecosystem
just made table stakes — REST and code execution.

## The surface matrix

"Every surface" is a finite, concrete list. The author writes
nothing for any column.

| Surface | Who reaches for it | Status |
|---|---|---|
| Local CLI | A human at a terminal | Ships today (Typer, ADR 0001) |
| Local MCP (stdio) | An agent on the same machine | Ships today (`packages.mcp`) |
| Remote MCP (streamable HTTP) | An agent over the network | Ships today (auth recipe ADR 0011) |
| Remote REST / OpenAPI | Any HTTP client, non-MCP agent, `curl`, generated SDKs | **New** |
| Remote CLI | A human or script driving a deployed instance | **New** (thin wire client) |
| Code execution | A token-efficient agent | **New** (sandboxed) |
| Typed SDKs ("Stainless mode") | Consumers who want a native client library | **Exploratory** |
| Web dashboard | A human who wants a visual console — browse, invoke, inspect | **Exploratory** |

The first three exist. The vision is the remaining five — and the
discipline that all eight derive from one tool definition with no
author effort.

## How an author experiences this

The composition root does not change. This is the canonical
`tracker/server.py` from the README, unchanged:

```python
import a2kit

app = a2kit.App("tracker")
app.add_router(TasksRouter())
# the author has written zero transport code
```

And every surface is already there:

```bash
tracker tasks list-tasks --project-id=abc   # local CLI, in-process
tracker serve --transport=stdio             # local MCP
tracker serve --transport=http              # remote MCP + REST + code-exec,
                                            #   one process, one port
```

A tool method stays pure business logic:

```python
class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(self, *, store: TaskStore, task_id: str) -> Task:
        return store.get(task_id)
```

That one method is, with no further work: a CLI subcommand with
`--task-id`, an MCP tool with a JSON schema, a REST `GET` route
with an OpenAPI entry, a readable code-execution module, and (if
Stainless mode lands) a typed SDK method. The typed signature is
the single source of truth; every surface is a projection of it.

## Design principles

These are the rules every OpenSpec change in service of this vision
must hold to.

### 1. Zero-config by default, opt-out by toggle

`a2kit.App("x")` yields an app that, when served, exposes every
applicable surface. The author does not opt **in** to REST, or to
code execution, or to the CLI. They are simply there. A toggle
exists only to turn a surface **off** — for a deliberate reason
(a locked-down deployment, a cold-start budget, a security
posture). The default is "all on." The exact toggle shape
(`serve --without=rest`, an `App(surfaces=...)` argument, config
file) is an open question for OpenSpec.

### 2. The tool definition is the single source of truth

Typed parameters and a typed return annotation already drive the
MCP schema and the CLI signature. They will equally drive the
OpenAPI document, the code-execution stub, and any generated SDK.
The author never restates a type for a second surface. If a surface
needs information the definition cannot carry, the fix is to extend
the definition surface (see principle 5), never to ask the author
to write surface-specific glue.

### 3. The author writes business logic, never plumbing

No transport library is imported in tool code. No surface appears
in a tool's signature. This already holds for CLI and MCP
(ADR 0002 — `pydantic.Field` is the only annotation surface;
ADR 0003 — semantic flags are transport-neutral). Every new surface
must preserve it. The day an author has to write REST-specific or
sandbox-specific code in a tool body, the vision has failed.

### 4. Surfaces are adapters, never peers

There is one dispatch core (`Container.dispatch`). Each surface is
a thin lift over it — a projection on the way out, a parse on the
way in. A surface adapter may be deleted without touching another.
Adding a surface must never bend the core's shape. If a new surface
*does* force a core change, that change is a first-class ADR, not a
quiet concession. This is the structural answer to "is mixing
interfaces in one codebase a mistake?" — it is not, *provided*
surfaces stay adapters and never become peers that negotiate with
each other.

### 5. Semantics travel; transports interpret

The transport-neutral vocabulary already exists: `visibility`
(`hidden` / `cli` / `all`), `idempotent`, `destructive`,
`open_world`. Each surface reads it as it sees fit — MCP lifts it to
`ToolAnnotations`, the CLI to `--help` warnings. The new surfaces
extend this, not bypass it:

- **REST** routes verbs by semantics — a `@read` becomes `GET`, a
  `@write` becomes `POST`/`PUT`, `destructive` informs `DELETE`.
  ADR 0003 already names "future REST method routing" as an
  intended consumer of this vocabulary.
- **Code execution** gates capabilities by the same flags — a
  `destructive` tool is reachable from the sandbox only under an
  explicit capability grant.

The `visibility` tier likely needs a fourth value (or a re-modelled
axis) once REST is real: today it is a CLI-vs-MCP split, and "this
tool is CLI-only, never REST" is a distinct intent. That is an
ADR-worthy extension of ADR 0003's locked four-entry vocabulary —
flagged here, decided in OpenSpec.

### 6. The cold-start budget is sacred

`import a2kit` stays under 100 ms. FastMCP is already confined to
`a2kit.packages.mcp` and loads only on `serve`. Every new surface
obeys the same rule: REST framework, sandbox runtime, and SDK
codegen dependencies live in their own `a2kit.packages.*` modules
and are imported only when that surface is actually served. A
surface being "on by default" means *available*, not *eagerly
imported*.

### 7. Lean on mature SDKs now; the interface is the contract

Every surface ships **first** as a thin layer over an existing,
mature SDK — FastMCP for MCP, Typer for the CLI, an established
framework for REST. The initial implementation is therefore
**heavy**: a wide dependency tree, more code a2kit does not own,
less control. That is an accepted, deliberate trade.

The bet underneath it: **the interaction interface — the
author-facing API and the consumer-facing wire shape — is the real
contract; the implementation beneath it is swappable.** Once a
surface is proven and its interface has stabilised, the heavy SDK
under it can be replaced with a thin, fast, purpose-built
implementation **with no change visible to tool authors or
consumers.** Build on the ecosystem's shoulders to ship; earn the
right to go thin later by first freezing the interface.

This composes cleanly with principle 6 — a heavy SDK is tolerable
precisely because it is confined to its own `a2kit.packages.*`
module and lazily imported, so it never taxes cold start. And it
does not conflict with the no-backward-compatibility rule: the
later rewrite changes the implementation, never the interface, so
there is nothing for a consumer to migrate. ADR 0001 already
reasons this way — Typer replaced a hand-rolled reflection layer,
and the CLI *interface* was held stable for the planned Rust and
TypeScript ports.

## Code execution, bundled

Code execution is not a separate product an author installs. It is
a surface a2kit's MCP server exposes **by default**, built from the
same tool definitions:

- Tool definitions are projected as **readable code modules** in a
  virtual filesystem the agent can list and read on demand —
  progressive disclosure instead of a giant up-front tool catalog.
- A **`search_tools`** entry point lets the agent find the right
  module without reading the whole tree.
- A **sandboxed interpreter** runs agent-authored code that calls
  those tools. FastMCP 3.2 already ships this machinery —
  `experimental.transforms.CodeMode` with a `MontySandboxProvider`
  backed by `pydantic-monty` (the same Monty lineage a limited
  code-execution sandbox was once built on here), resource limits,
  a tool-callback bridge, and `search` / `get_schemas` discovery
  tools. Per principle 7, a2kit adopts that machinery rather than
  rebuilding it; the `SandboxProvider` protocol keeps the runtime
  swappable later. The requirement a2kit adds on top is
  **capability-gating by the semantic flags from principle 5** —
  stock `CodeMode` exposes every tool to the sandbox
  indiscriminately. The other concern — whether sandboxed tool
  calls carry a2kit's request-scoped DI and connection scope — is
  settled: a spike proved they do, through the unmodified dispatch
  wrapper, with zero framework changes (see
  [`SPIKE_CODE_EXEC_DI.md`](SPIKE_CODE_EXEC_DI.md)).

The author does nothing. The 98.7%-token-reduction win that the
ecosystem is chasing arrives as a property of the framework, not as
a thing each tool author re-implements.

### Toggle and per-surface exposure

Code execution is **on by default** and turned off with a single
toggle (shape TBD — e.g. `serve --code-mode-off`), consistent with
principle 1. Where it is exposed is deliberately not uniform:

- **MCP and remote MCP** — exposed, as **one global `execute`-style
  tool** whose sandbox can reach every tool the server holds.
- **CLI** — exposed, as a single global subcommand with the same
  reach.
- **REST** — **not** exposed. REST consumers call typed endpoints
  directly and are not the token-constrained agents code execution
  exists to serve; a "POST arbitrary code" endpoint is also the
  wrong shape for a REST API.

The toggle is load-bearing for the gateway (next section). When
a2kit gains an MCP gateway mode, the gateway becomes the single
place code execution should live — it exposes the one code-mode
tool spanning every backend, and each backend a2kit MCP runs with
code mode **off**, so the capability is not redundantly duplicated
behind the gate.

## The gateway horizon

ADR 0012 decided **no gateway** — and that decision stands for the
problem it actually addresses: fanning *authentication* in across
multiple standalone MCP servers. That remains correct at current
scale.

This vision introduces a **different** gateway on a **different**
axis, and the distinction must stay sharp so a future ADR is not
confused with 0012:

- **0012's gateway** aggregates **auth** — one OAuth gate in front
  of N servers. Rejected; each server stays standalone.
- **The code-mode gateway** aggregates **capability** — a single
  MCP tool (`run_code` / `execute`) whose sandbox can reach the
  tools of *every* registered a2kit server. One tool in the agent's
  context, the entire fleet's capability behind it. This is the
  natural endgame of code-execution-with-MCP once more than one
  a2kit server is in play. Each backend a2kit MCP behind the gate
  runs with code mode **off** (per the toggle above); the gateway
  holds the sole code-mode tool, so the capability is exposed once,
  not once per backend.

These are orthogonal, but they intersect: a code-mode gateway that
spans N servers is itself a re-evaluation trigger for ADR 0012 (its
own re-evaluation clause fires at "server count exceeds 3" and at
"the gateway ecosystem matures"). When the code-mode gateway is
specified, the auth topology gets re-opened **jointly** with it, in
a paired ADR — not silently. This section is the standing note that
the future change is expected and is not a contradiction of 0012.

The code-mode gateway is explicitly **later** — it presupposes the
single-server code-execution surface exists and is proven first.

## Exploratory surfaces

Two further surfaces are plausible projections of the same single
tool definition. Both are marked exploratory on purpose — pulled in
by real demand, not pushed speculatively — and nothing downstream
depends on either.

### Stainless mode — typed SDKs

Generating typed client SDKs from the tool definitions, aimed at
consumers who want a native library instead of a transport. If the
REST surface produces a clean OpenAPI document (Phase 1), this
surface becomes nearly free: OpenAPI is exactly what an SDK
generator ingests. Open question for OpenSpec — whether a2kit
generates SDKs itself, defers to Stainless as a tool, or declines
the surface entirely.

### Web dashboard

A browser console projected from the tool definitions — the tool
list as navigation, typed parameters as forms, typed returns
rendered as tables or detail views. It is the same projection model
as REST, rendered as HTML instead of JSON. Potentially a large
quality-of-life surface in the long run: an operator-facing way to
browse, invoke, and inspect an a2kit server without an agent or a
terminal (mcp-memory-service ships exactly such a dashboard and its
users call it the feature they did not know they needed). Like
every other surface, the author writes nothing for it. FastMCP 3.2
ships `fastmcp.apps` — interactive MCP-UI components (forms,
choices, approvals, file upload) — which is a building block this
surface could lean on per principle 7. Open question for
OpenSpec — whether the dashboard is generated from the same
definitions, layered on the REST surface, or deferred until a
concrete operator need lands.

## What stays the author's job

The vision abstracts away surfaces, not the domain. The author
still owns:

- **Business logic** — the tool body.
- **Connection configuration schema** — the `ConnectionConfig`
  subclass (the framework wires it; the author declares its shape).
- **Identity-provider choice for authenticated deployments** — auth
  is MCP-mode wiring per ADR 0010 / 0011; the framework prescribes
  the recipe, the operator picks the IdP.

a2kit will **not**: make the author choose a transport, write
per-surface code, or hand-maintain a schema. Anything that would
force one of those is out of scope by construction.

## Staged delivery (rough)

Sequencing only — OpenSpec changes carry the real task breakdowns.

1. **REST / OpenAPI surface.** Highest leverage: it unlocks the
   remote-REST surface *and* makes the remote-CLI client trivial
   (the client just speaks REST). Reuses the existing type-driven
   formatter for content negotiation.
2. **Code-execution surface.** Filesystem tool projection,
   `search_tools`, sandboxed interpreter. Single-server scope.
3. **Remote CLI client.** A thin wire client (`a2kit` against a
   remote endpoint) — a sibling to the server, not a reshaping of
   it. Carries a token; auth is the deployment's, per ADR 0010.
4. **Stainless mode.** Only if a real consumer demand lands.
5. **Code-mode gateway.** Multi-server capability aggregation;
   paired ADR with an ADR 0012 re-evaluation.

## Open questions for OpenSpec

- **Capability gating and packaging, not sandbox choice.** FastMCP
  3.2 provides the runtime (`CodeMode` + `MontySandboxProvider`,
  swappable via the `SandboxProvider` protocol), and a spike proved
  sandboxed tool calls carry a2kit's request-scoped DI and
  connection scope unchanged (`SPIKE_CODE_EXEC_DI.md`). What remains
  for OpenSpec: capability-gating the sandbox by the semantic-flag
  vocabulary (stock `CodeMode` exposes every tool indiscriminately),
  packaging `pydantic-monty` as a lazily-imported optional
  dependency, and absorbing `CodeMode`'s `experimental`-namespace
  API churn against the `fastmcp<4` pin.
- **Toggle shape.** `serve --without=...`, `App(surfaces=...)`, a
  config file, or some combination. What is the unit of opt-out.
  Code execution needs its own off switch (`--code-mode-off`) in
  the same scheme.
- **REST construction.** Hand-rolled vs a framework (FastAPI) vs
  derived from the FastMCP server. How content negotiation maps the
  TSV / JSON / `page-tsv` formatter onto HTTP `Accept`.
- **Auth on REST and remote CLI.** ADR 0010 says the CLI never
  authenticates because it is local single-user. Remote REST is
  remote multi-user — it must authenticate like MCP. The remote-CLI
  *client* is then a token-carrying client, not an exception to
  ADR 0010. This needs an ADR confirming the reasoning.
- **`visibility` re-modelling.** Today's `hidden` / `cli` / `all`
  cannot express "REST-only" or "never REST." Extending it
  supersedes part of ADR 0003. Code execution's exposure (CLI and
  MCP, never REST) is a concrete case of the same "never REST"
  axis — though decided framework-side by a toggle, not per-tool by
  an author.
- **Process model.** One process multiplexing all surfaces vs
  separate processes per surface over a shared core (the
  mcp-memory-service pattern: shared backend, one process per
  transport).
