---
id: "0031"
status: accepted
date: 2026-06-28
last_reviewed: 2026-06-28
supersedes: []
superseded_by: null
tags: [surface, mcp, ui, auth, architecture, dependency]
deciders: [Denis Tomilin]
---

# ADR 0031: MCP Apps support — standard-first, Prefab-optional, mechanism-not-UI

## Status

Accepted, 2026-06-28. Delivered by the OpenSpec change `add-mcp-apps-support`.
Confirmed by the human (Constitution Phase A).

## Summary

In one sentence: a2kit serves MCP Apps (the `ext-apps` / `ui://` resource
standard) through the **existing `@app.mcp.*` escape hatch** — forwarding the
`app=` payload verbatim, importing no UI framework, and leaving the HTML bundle
to the consumer — while the auth gap this work uncovered (`authorize=` silently
dropped on `@app.mcp.*`) is closed by enforcing the gate at registration time.

## The problem

MCP Apps let a tool return an interactive `ui://` HTML resource that a host
renders in a sandboxed iframe (MIME `text/html;profile=mcp-app`), with the
iframe calling tools back over a `postMessage` bridge. Consumers (a2kay's
job dashboards, enrichment-review forms) will want this. Spike work against
`fastmcp 3.4.2` established that custom-HTML MCP Apps **already work today**
through a2kit's `@app.mcp.tool`/`@app.mcp.resource` family — the `app=AppConfig(...)`
payload forwards verbatim. The questions were therefore not "can we" but
"what is a2kit's *role*, and what must we document, test, and decline."

While grounding the design we found a security drift: `authorize=` on
`@app.mcp.*` is captured (`McpRegistration.authorize`) but consumed nowhere,
contradicting the `tool-authorization` spec's promise that `authorize=` is
enforced uniformly across surfaces — including `@app.mcp.<feature>`. The drift
survived because that requirement's only scenario exercised a projection verb.

## What we decided

1. **Support the `ext-apps` standard, never bind to Prefab.** Prefab (Prefect's
   "dynamic UI"), mcp-ui, Skybridge, and hand-written HTML all compile to the
   same `ui://` resource + `_meta.ui` shape. a2kit targets that shape and stays
   blind to the producer. Prefab is a *consumer-installed* option (`app=True`
   forwards verbatim; `import prefab` is never a2kit's), mixable per-tool with
   custom HTML. Binding to Prefab's DSL would couple a2kit to one vendor
   framework and violate its data-plane identity.

2. **Ratify the escape hatch; add no new authoring surface.** Custom-HTML and
   Prefab apps already forward through `@app.mcp.tool`/`@app.mcp.resource`. This
   change documents and tests that path rather than inventing a parallel one
   (AGENTS.md §2). The example and the wire test are the contract.

3. **The shell-vs-data-verb split is the pattern.** The UI shell
   (`@app.mcp.tool(app=...)`) is MCP-pinned presentation and needs no dispatch
   pipeline. The interactive data the iframe calls back flows through ordinary
   projection verbs (`@a2kit.read`/`@a2kit.write(surfaces=("mcp",))`) that ride
   the full pipeline (auth, Principal, format-routing). Because MCP Apps
   interactivity decomposes into separate `tools/call` invocations, shell and
   data are naturally different tools — no machinery keeps them apart.

4. **a2kit ships mechanism, never builds UI.** a2kit projects and serves; it does
   not generate, bundle, transform, or render UI bytes. No `prefab-ui` / React /
   bundler dependency is added. The HTML/JS/CSS served by a `ui://` resource
   originates solely from the consumer's resource function. (Roles 1–2 — backend
   verbs and serving the bundle — are in scope; Role 3 — building the UI — is
   out, that is Prefab/Skybridge/FastUI territory.)

5. **Enforce `authorize=` on `@app.mcp.*` at registration time.** The escape
   hatch bypasses the dispatch pipeline, so the gate cannot ride
   `AuthorizeGateStage`. Instead `_register_mcp_surface` applies the captured
   `authorize=` to the substrate-wrapped callable, reusing the one shared
   `_run_authorize_gate` evaluation (single auth semantics, AGENTS.md §2); on
   denial it converts `AuthorizationDenied` to a `ToolError` so the existing
   `TypedErrorEnvelopeMiddleware` renders the same `{"error": envelope}` wire
   shape as every other surface. This honors the `tool-authorization` "uniform
   across surfaces, no auth gaps" requirement. We rejected the alternative —
   loudly rejecting `authorize=` on the hatch — because it would walk back that
   guarantee and make a class of tools permanently ungatable.

6. **Test the wire, not the pixels.** The capability test asserts the `ui://`
   resource's `_meta.ui.resourceUri`, MIME, and CSP — the altitude a2kit already
   tests JSON/TSV/page-tsv at. Rendering is the host's concern; manual smoke
   against the `ext-apps` `basic-host` or MCPJam stays out of CI.

## Consequences

- MCP Apps support is documented (`docs/patterns/mcp-apps.md`), exemplified
  (`examples/mcp_app/`), and wire-tested. "Does a2kit support MCP Apps?" → yes,
  via the escape hatch, no new surface.
- `authorize=` on `@app.mcp.*` is now enforced. This is behavior-tightening on a
  previously-ungated path: any caller relying on the old silent drop was already
  insecure, so honoring the kwarg can only tighten (AGENTS.md §1 — correctness
  fix, not a compat break).
- a2kit takes on no UI dependency and no UI-construction responsibility.

## Deferred (recorded to prevent scope creep)

- **A first-class typed UI return type** (`UIResource` / `ui=` on projection
  decorators, "Posture B"). The shell-vs-data split makes it largely a
  non-problem — the data the iframe needs is always a separate, already-typed
  projection verb. Revisit **only** if a consumer needs a *single* tool to be
  both full-pipeline and UI-bearing (e.g. a UI shell that must itself be
  gated/typed beyond what registration-time `authorize=` already gives).
