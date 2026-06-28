## Why

MCP Apps (the `ext-apps` / `ui://` resource standard, jointly published by
Anthropic + OpenAI as SEP-1865) let a tool return an interactive HTML UI that
the host renders in a sandboxed iframe. Spike work proved a2kit already serves
these today through the existing `@app.mcp.*` escape hatch with zero code
change — but the capability is undocumented, untested, and "works by accident."
While grounding the design we also found a security drift: `authorize=` on
`@app.mcp.*` is captured but never applied, silently violating the
`tool-authorization` spec's promise of uniform enforcement across surfaces.
This change turns the accidental capability into a supported, tested one and
closes the auth drift.

## What Changes

- **Document + prove MCP Apps support, standard-first.** a2kit serves `ui://`
  UI resources via the existing `@app.mcp.tool(app=AppConfig(resourceUri=...))`
  + `@app.mcp.resource(uri="ui://...", app=AppConfig(...))` escape hatch. The
  `app=` payload forwards verbatim; the resource is served with MIME
  `text/html;profile=mcp-app`. No new authoring surface is introduced — this
  ratifies what already forwards.
- **Framework-agnostic by construction.** a2kit imports no UI framework. Custom
  HTML and Prefab (`app=True` + a consumer-installed `prefab-ui`) both forward
  through the same seam and may be mixed per-tool. a2kit binds to the `ext-apps`
  *standard*, never to Prefab.
- **Codify the shell-vs-data-verb split.** The UI shell (`@app.mcp.tool(app=...)`,
  MCP-pinned, presentation) is distinct from the interactive data verbs the
  iframe calls back, which are ordinary projection verbs
  (`@app.read`/`@app.write(surfaces=("mcp",))`) that ride the full dispatch
  pipeline (auth, Principal, format-routing).
- **Fix the `authorize=` enforcement drift on `@app.mcp.*`** so the captured
  callable is actually enforced at registration time (the escape hatch bypasses
  `AuthorizeGateStage`, so a standalone gate is applied), honoring the existing
  `tool-authorization` "uniform across surfaces" requirement. A falsy return
  raises `AuthorizationDenied`, identical in shape to the projection path.
- **Ship a working example, a wire-level test, a docs page, and ADR 0031.**
  The test asserts the `ui://` resource wire shape (`_meta.ui.resourceUri`,
  MIME, CSP) — not pixels. ADR 0031 records the standard-first / Prefab-optional
  / "a2kit ships mechanism, never builds UI" decision and the deferred trigger
  for a first-class typed UI return type.

## Capabilities

### New Capabilities

- `mcp-apps`: Serving MCP App `ui://` UI resources through the `@app.mcp.*`
  escape hatch — standard-first (`ext-apps`), framework-agnostic (custom HTML or
  Prefab, a2kit imports neither), wire-shape guaranteed (MIME, `_meta.ui`), and
  the shell-vs-data-verb division of labor. a2kit ships the projection
  mechanism; it never constructs, bundles, or renders UI.

### Modified Capabilities

- `tool-authorization`: The existing "`authorize=` enforcement is uniform
  across surfaces" requirement names `@app.mcp.<feature>` but the escape-hatch
  path never applied the gate. The requirement is clarified (the `@app.mcp.*`
  path enforces at registration time since it bypasses the dispatch pipeline)
  and gains a scenario that actually exercises `@app.mcp.*` enforcement.

## Impact

- **Code:** `src/a2kit/packages/mcp/server.py` (`_register_mcp_surface` applies
  the captured `authorize=`); a small shared gate helper reused from the
  `AuthorizeGateStage` logic to avoid §2 redundancy. No change to the
  `@app.mcp.*` authoring signature.
- **Tests:** new `tests/packages/mcp/` wire test for the `ui://` resource shape;
  new `@app.mcp.*` `authorize=` enforcement test (the missing BDD scenario).
- **Examples:** new `examples/mcp_app/` (shell tool + HTML resource + a
  projection data verb the iframe calls back).
- **Docs:** new "Serving MCP Apps from a2kit" page; ADR 0031.
- **Dependencies:** none added. `fastmcp` stays pinned `>=3.2,<4` (resolving
  3.4.2, which carries the `ui://` / `AppConfig` API). `prefab-ui` is never a
  dependency — consumer-installed only.
- **Out of scope (deferred):** a first-class typed `UIResource` return type /
  `ui=` on projection decorators (Posture B). Recorded in ADR 0031 with its
  revisit trigger.
