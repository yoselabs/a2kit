## Context

MCP Apps (`ext-apps`, SEP-1865) standardize interactive `ui://` UI resources
rendered in a sandboxed host iframe. A tool declares `_meta.ui.resourceUri`
pointing at a `ui://` resource; the host fetches the resource (MIME
`text/html;profile=mcp-app`), renders it, and the iframe talks back to the host
over a `postMessage` JSON-RPC dialect — which decomposes into ordinary
`tools/call` invocations.

Spike work (against `fastmcp 3.4.2`, the current resolution of the `>=3.2,<4`
pin) established the ground truth:

- **Custom-HTML MCP Apps already work** via a2kit's existing `@app.mcp.*`
  escape hatch. `@app.mcp.tool(app=AppConfig(resourceUri="ui://x"))` yields wire
  `_meta.ui.resourceUri`; `@app.mcp.resource(uri="ui://x", app=AppConfig(csp=...))`
  serves the bundle as `text/html;profile=mcp-app`. The `app=` payload forwards
  verbatim through `server.py::_register_mcp_surface`.
- **Prefab is not a hard dependency** (`import prefab` → `ModuleNotFoundError`).
  `app=True` (Prefab's trigger) forwards verbatim too. a2kit is blind to which
  UI framework, if any, a tool uses.
- **`@app.mcp.*` registrations bypass the dispatch pipeline** (no
  format-routing, no `AuthorizeGateStage`, no call-scope/Principal seeding; DI
  still resolves via `install_substrate_signature`). This is deliberate — the
  hatch is substrate-native.
- **`authorize=` on `@app.mcp.*` is silently dropped.** It is captured into
  `McpRegistration.authorize` (`surface.py`) but consumed nowhere, contradicting
  the `tool-authorization` spec, which already lists `@app.mcp.<feature>` as a
  surface where `authorize=` is enforced uniformly. The drift survived because
  that requirement's only scenario exercises a projection verb.

## Goals / Non-Goals

**Goals:**
- Ratify and document MCP Apps support standard-first, with a wire-shape test,
  a working example, a docs page, and a recorded decision (ADR 0031).
- Close the `authorize=` enforcement drift on `@app.mcp.*` so the escape hatch
  is not an authorization gap, honoring the existing `tool-authorization` spec.
- Keep a2kit framework-agnostic: custom HTML and Prefab mix per-tool; a2kit
  imports neither.

**Non-Goals:**
- Building, bundling, or rendering UI (Role 3). a2kit ships the projection
  mechanism; the HTML/JS bundle is authored and served by the consumer. No
  `prefab-ui`/React/bundler dependency is added.
- A first-class typed `UIResource` return type or `ui=` on projection
  decorators (Posture B). Deferred with a recorded trigger.
- Host-side rendering, the `postMessage` bridge, or any iframe runtime — those
  belong to the MCP host, not the server framework.

## Decisions

**D1 — Support the `ext-apps` standard, never bind to Prefab.** Prefab,
mcp-ui, Skybridge, and hand-written HTML all compile to the same `ui://`
resource + `_meta.ui` shape. a2kit targets that shape and forwards `app=`
verbatim. Binding to Prefab's DSL would couple a2kit to one vendor framework and
violate its data-plane identity. *Alternative considered:* a Prefab integration
helper — rejected (coupling, and it adds nothing the verbatim forward doesn't
already give).

**D2 — No new authoring surface; ratify the escape hatch.** Custom-HTML and
Prefab apps already forward through `@app.mcp.tool`/`@app.mcp.resource`. This
change documents and tests that path rather than inventing a parallel one
(AGENTS.md §2). The example and the wire test *are* the contract.

**D3 — The shell-vs-data-verb split is the recommended pattern, not enforced.**
The UI shell (`@app.mcp.tool(app=...)`) is MCP-pinned presentation and needs no
dispatch pipeline. The interactive data the iframe calls back flows through
ordinary projection verbs (`@app.read`/`@app.write(surfaces=("mcp",))`) that
ride the full pipeline (auth, Principal, format-routing). Because MCP Apps
interactivity decomposes into separate `tools/call` invocations, shell and data
are naturally different tools — no framework machinery is needed to keep them
apart. Documented in the docs page and the example; not code-enforced.

**D4 — Enforce `authorize=` on `@app.mcp.*` at registration time.** The escape
hatch bypasses `AuthorizeGateStage`, so the gate cannot ride the pipeline.
Instead `_register_mcp_surface` applies the captured `authorize=` to the
substrate-wrapped callable before handing it to FastMCP, reusing the
`AuthorizeGateStage` evaluation logic (resolve callable params via
`Container.call_scope`; falsy → `AuthorizationDenied`) so there is one auth
semantics, not two (AGENTS.md §2). This honors the existing
`tool-authorization` "uniform across surfaces" requirement. *Alternative
considered:* reject `authorize=` loudly on the hatch — rejected because it walks
back the spec's "no auth gaps" guarantee and makes a class of tools permanently
ungatable.

**D5 — Test the wire, not the pixels.** The capability test asserts the `ui://`
resource's `_meta.ui.resourceUri`, MIME `text/html;profile=mcp-app`, and CSP —
the same altitude a2kit already tests JSON/TSV/page-tsv at. Rendering is the
host's concern; manual smoke against `basic-host`/MCPJam is out of CI.

## Risks / Trade-offs

- **[Authoring `AppConfig` by hand is verbose.]** → Accepted for now; a typed
  helper risks coupling and is premature. Revisit only with consumer friction
  (the Posture-B trigger).
- **[Enforcing `authorize=` at registration duplicates gate logic.]** →
  Mitigated by extracting/reusing the single `AuthorizeGateStage` evaluation
  helper rather than reimplementing it; one auth semantics across surfaces.
- **[Enforcement changes behavior for any existing `@app.mcp.*` tool that
  passed `authorize=`.]** → Today such a tool is silently ungated, so any caller
  relying on it is already insecure; honoring it can only tighten, never loosen.
  No external consumer is known to pass `authorize=` on `@app.mcp.*`. Per
  AGENTS.md §1 this is a correctness fix, not a compat-breaking feature removal.
- **[Prefab path is untested in CI (optional dep).]** → Documented as
  consumer-opt-in; a2kit only guarantees the verbatim forward and the
  no-UI-framework-import property, both of which are tested.

## Migration Plan

No data migration. The `authorize=` enforcement fix is behavior-tightening on a
path that was insecure; shipped in a normal release with a CHANGELOG note. The
example, docs, and ADR 0031 are additive.

## Open Questions

- None blocking. The Posture-B trigger (a single tool that must be both
  full-pipeline and UI-bearing) is recorded in ADR 0031 as the condition to
  reopen the first-class-UI-return question.
