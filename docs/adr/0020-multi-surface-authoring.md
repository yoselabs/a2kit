---
id: "0020"
status: accepted
date: 2026-05-23
last_reviewed: 2026-05-23
supersedes: []
superseded_by: null
tags: [architecture, surface, http, mcp, di, signature]
deciders: [Denis Tomilin]
---

# ADR 0020: Multi-surface authoring — one typed function, every transport

## Status

Accepted, 2026-05-23. Lands `add-multi-surface`, deletes
`packages/rest.py`, adds `packages/http/`. Breaking change to
`build_parent_app(app, *, mcp, rest)` and `serve --mcp-only` /
`--rest-only` CLI flags.

## Summary

In the context of a2kit's value proposition — write one typed Python
function, expose it over every transport — facing the fact that the
pre-v0.34 surface delivered this only for MCP (the FastAPI side was a
65-LOC stub serving `/health` and an empty `/openapi.json`), and that
authors who wanted real REST routes were forced into `Depends(...)`
fragmenting the framework's DI contract, we **landed a three-decorator
family on `App` driven by one signature-rewriting mechanism** so a
single tool body reaches FastMCP and FastAPI natively without duplicate
code paths in author space. **Achieving** native FastAPI semantics
(`response_model`, status codes, middleware, OpenAPI), native FastMCP
semantics (Context, Prompts, Resources), per-request DI scope on the
HTTP path, and cold-start preservation (`import a2kit` still does not
load `fastapi` or `fastmcp`). **Accepting** two FastMCP code paths
(projection through the dispatch pipeline; substrate-native through
`install_substrate_signature`) as the price of preserving the
byte-for-byte MCP test guarantee while making `@app.mcp.tool` a real
first-class surface.

## Context

a2kit positions itself as a single-source-of-truth toolkit: define a
typed async function once, get CLI, MCP, and HTTP exposure. The MCP
half has worked since v0.1 — `install_mcp_signature` rewrites the wire
signature so FastMCP introspects only the agent-facing params; the
dispatch pipeline opens `Container.call_scope` and resolves a2kit DI
per call.

The HTTP half had not. `packages/rest.py` was a deferred stub. Authors
wanting real REST routes had three bad options: drop to FastAPI
directly (losing a2kit DI), pollute their tool signatures with
`Depends(...)` markers (breaking the "type annotation alone" contract),
or maintain two parallel implementations of the same logic.

The architectural review surfaced four hard constraints that any
fix had to satisfy:

1. **No author-visible `Depends(...)`**. a2kit DI is type-driven by
   construction.
2. **Native substrate primitives**. FastAPI's `Request`, `Response`,
   `BackgroundTasks`, `WebSocket` and FastMCP's `Context` must pass
   through to the substrate, not be intercepted by a2kit's DI graph.
3. **Per-request DI scope on HTTP**. Existing MCP guarantees from ADR
   0009 (`di-per-call-scope`) must hold on the FastAPI side. A
   `Scope.SCOPED` provider returns a fresh instance per request even
   under concurrent load.
4. **Cold-start preservation**. `import a2kit` cannot load `fastapi`
   or `fastmcp` (~150ms each on cold machines).

A separate audience question — whether the HTTP surface is even
necessary given MCP coverage — was settled empirically by inspecting
the `doobidoo/mcp-memory-service` repository: 91% of its REST
endpoints (dashboards, ops, sync, OAuth, SSE) have no MCP equivalent.
HTTP is not redundant; it is the deterministic surface for
framework consumers (LangGraph, CrewAI), dashboards, and ops
tooling.

## Decision

Three decorator families on `App`, all classified by **one**
signature-rewriting mechanism in `packages/dispatch/substrate.py`:

```python
@app.read         async def fetch(*, id, db: Database) -> Memory: ...          # both surfaces
@app.read(expose=("mcp",))   async def llm_fetch(...): ...                     # MCP only
@app.api.get("/version", response_model=V)
                  async def version(*, db: Database) -> V: ...                 # FastAPI native
@app.mcp.prompt(name="summarize")
                  async def summarize(*, topic, db: Database) -> str: ...      # FastMCP native
```

Mechanism: `split_signature(fn, substrate, container)` classifies each
parameter into one of three buckets:

1. **Substrate-reserved** — annotation in the frozen per-substrate
   allowlist; passes through to the wrapper signature for substrate
   population.
2. **Container-known** — `container.has_provider(annotation)` is true;
   resolved by `Container.call_scope` inside the wrapper body.
3. **Wire** — everything else; substrate routes from request
   body/query/path/form.

Frozen allowlists:

```python
_FASTAPI_RESERVED = {Request, Response, BackgroundTasks, WebSocket}
_FASTMCP_RESERVED = {Context}
```

Extending the allowlists requires an ADR 0020 amendment plus the
one-line frozenset edit. The `tests/packages/dispatch/test_substrate.py::
test_fastapi_reserved_baseline` test asserts exact membership against
the baseline so any unrecorded change fails CI.

Cross-substrate misclassification (e.g. `ctx: Context` on the FastAPI
substrate) raises `SubstrateSignatureError` at install time, naming
the offending parameter and the substrate where the type IS reserved.

`install_substrate_signature(fn, substrate, container)` returns the
substrate-facing wrapper:

- `__signature__` lists only reserved + wire params (substrate
  introspection sees a clean surface).
- Wrapper body opens `Container.call_scope`, resolves Container-known
  params, merges substrate-populated reserved kwargs, calls `fn`.
- Sets `_a2kit_scope` contextvar (sentinel marker; reset on exit).

For the FastAPI surface this is the primary entry point. For the
FastMCP surface there are **two code paths by design** (see
Consequences §1).

Auto-mount: `serve --transport=http` mounts each substrate sub-app
only if the runtime carries registrations for it. Projection tools
default to both (`expose=("mcp", "api")`); the `expose=` kwarg on
projection decorators narrows. Empty `expose` raises `ValueError` at
decoration. If neither substrate has registrations,
`build_parent_app` raises `ValueError`.

`authorize=` kwarg captured uniformly across all three families.
Enforcement deferred to `add-auth` (proposal-only); the kwarg surface
lands here so authors do not have to refactor signatures later.

Test seam for swapping a2kit-resolved deps in FastAPI tests:
**re-provide on a fresh `App` before `build()`** (last-write-wins).
FastAPI's `app.dependency_overrides[T] = fake` does NOT work for
Container-known types — it keys on `Depends` callables. Documented
positively in `tests/packages/http/test_dependency_override.py`.

`packages/rest.py` is deleted outright per AGENTS.md §1; Python's
native `ModuleNotFoundError: No module named 'a2kit.packages.rest'`
satisfies the loud-crash requirement.

## Consequences

**1. Two FastMCP code paths coexist by design.**

The Phase 1 implementation began with the intent to unify both paths
under `install_substrate_signature`. The existing
`install_mcp_signature` is entangled with MCP-specific concerns
(`Context` injection by author-declared name, connection-scope
synthesis, return-annotation copy with `_WARN_ONCE`) and is folded
into the dispatch pipeline (timeout, enricher, dispatch-hook with DI,
log ambient, error-capture, error-render). Migrating it carried real
regression risk for 200+ MCP tests under the "byte-for-byte" gate.

**Option B was locked**: per-substrate emission, classifier shared.

- Projection tools (`@a2kit.read/list/write`) → dispatch pipeline +
  `install_mcp_signature`. Unchanged.
- Substrate-native (`@app.mcp.tool/.prompt/.resource`) →
  `install_substrate_signature`. Bypasses the dispatch pipeline (no
  log ambient, no projection format routing) because that is the
  whole point of the FastMCP-native family — authors who want
  framework-native behaviour use `@a2kit.read`.

The two paths are visible to anyone reading `build_mcp_server`. The
shared classifier (`split_signature`) keeps the "one mechanism" spirit
even though the wrapper emission is per-substrate.

**2. POST-for-all routing on projection tools.**

`@a2kit.read async def fetch(*, id: str)` becomes `POST /api/fetch`
with `{"id": "x"}` in the body — RPC-shape, mirroring MCP's
`tools/call`. RESTful verb-mapping (`@a2kit.read` → `GET`,
`@a2kit.write` → `POST/PUT/DELETE`) was rejected because it splits
each tool's contract across two HTTP methods (one for the tool
itself, one for the params) and complicates pydantic schema
generation. `GET /api/fetch` returns 405 — the response is honest
about the contract. Authors who want native REST verb mapping use
`@app.api.get(...)`.

**3. `serve --transport=http` is now opinionated about substrate
selection.**

Pre-v0.34 the CLI accepted `--mcp-only` / `--rest-only` flags. Both
are removed. Substrate selection is structural now: registration
shape determines mount shape. Operators who want to narrow at deploy
time use `--select 'surface=mcp'` / `--select 'surface=api'` from
`add-tool-select` (orthogonal change, depends on this one). This
makes "did I forget a flag?" a non-question — if the app has
`@app.api.*` routes, the FastAPI sub-app mounts.

**4. Cold-start invariants tightened.**

`import a2kit` does not load `fastapi`, `fastmcp`, or the
`packages/http` build module. `App.api` and `App.mcp` properties
return plain dataclasses; the substrates load on first
`build_http_app` / `build_mcp_server` call. The `packages/http/
__init__.py` uses PEP 562 `__getattr__` to defer `build_http_app`
loading until it is attribute-accessed. Tests in
`tests/test_cold_start.py` codify all of this.

**5. The substrate-reserved allowlists are an extension point.**

When FastAPI or FastMCP adds a new type-injected primitive (similar
to `BackgroundTasks`), this ADR amends with a one-line frozenset edit
in `packages/dispatch/substrate.py` and the matching test baseline.
Detected by the `test_fastapi_reserved_baseline` and
`test_fastmcp_reserved_baseline` tests asserting exact membership.

## Related

- ADR 0009 — Per-call DI scope. The HTTP wrapper opens
  `Container.call_scope` per request; this ADR extends 0009's
  contract to the HTTP path.
- ADR 0014 — Consumer-aware format routing. Projection tools on
  `/api` skip the MCP format-routing middleware; FastAPI returns JSON
  by default.
- ADR 0019 — App / AppRuntime split. `runtime.api_surface` /
  `mcp_surface` are populated by `build()` from the source App's
  decorator accumulators.
- `add-tool-select` (separate change) — `--select 'surface=mcp'`
  runtime filter; depends on this one.
- `add-auth` (proposal-only) — turns `authorize=` from kwarg surface
  into enforcement; FastMCP-native OAuth wrappers under
  `a2kit.auth.*`.

## Supersedence: `dependency_overrides[T]` (closed 2026-05-24)

The "`app.dependency_overrides[T] = fake` does NOT work for a2kit-resolved types" clause above is SUPERSEDED by the [[bridge-container-fastapi-depends]] change. `Container.expose_as_fastapi_depends(T)` now publishes a FastAPI-compatible resolver for any container-known type; `build_http_app` registers it in `fastapi_app.dependency_overrides` per type used by any descriptor. A per-request middleware opens the a2kit child container and publishes it on the `_a2kit_request_scope` contextvar before FastAPI dependency resolution runs.

The canonical test seam for swapping a2kit-DI'd deps in FastAPI handler tests remains `container.override(T, fake)` (ADR 0006). `app.dependency_overrides[T] = fake` now ALSO works for container-known types — but the canonical seam is preferred because it composes cleanly with `container.snapshot()`-based test isolation.

## Supersedence (partial): Surface Protocol landed (2026-05-25)

The "`Substrate = Literal["fastapi", "fastmcp"]` discriminator" architecture this ADR records is SUPERSEDED in part by [[add-surface-protocol-additive]] + [[remove-substrate-literal]]. Surface identity now flows through `Surface` objects from `a2kit.packages.dispatch.surface`; `split_signature` / `install_substrate_signature` take a `Surface` and consume its `reserved_types` / `substrate_dep_markers` attributes directly. `Substrate` no longer exists; access raises with a hint pointing to `Surface`. `ToolDescriptor.expose` widened from `tuple[Literal["mcp","api"], ...]` to `tuple[str, ...]`. `build_parent_app` walks `SURFACE_REGISTRY` instead of hardcoded `_has_*_registrations` helpers.

## Standing: "Two FastMCP code paths coexist by design" (2026-05-25)

The Option-B clause in §Consequences (above) stands. [[unify-signature-installers]] was scoped, attempted, and dropped as SUPERSEDED-by-architecture: the two installers serve different layers — `install_mcp_signature` relabels `__signature__` on a prefolded dispatch pipeline, `install_substrate_signature` wraps a fn body from scratch. Naively replacing one with the other erases the folded pipeline from MCP (log ambient, format routing, error capture) — a regression, not a refactor.

The honest unification path requires first folding the transport-neutral dispatch pipeline on the HTTP path (gaining log / format-routing / error-capture on FastAPI — actually desirable). Then both paths become "fold pipeline + relabel signature," which is a real consolidation. That work is gated as a separate future change; the §2-no-redundancy debt note here remains accurate but its discharge is deferred until HTTP folds the pipeline.
