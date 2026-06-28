# Serving MCP Apps (`ui://` interactive UI)

MCP Apps (the `ext-apps` standard, SEP-1865) let a tool return an interactive
HTML UI that an MCP host renders in a sandboxed iframe. a2kit serves them
through the **existing `@app.mcp.*` escape hatch** — there is no dedicated UI
authoring surface, and a2kit imports no UI framework. See
[ADR 0031](../adr/0031-mcp-apps-support.md) for the decision and its bounds.

## The shape: a UI shell + a UI resource + data verbs

```python
import a2kit

class RegionsRouter(a2kit.Router):
    slug = "regions"

    # The DATA the UI calls back for — an ordinary projection verb.
    # Rides the full pipeline: authorize=, Principal, format-routing.
    @a2kit.read(surfaces=("mcp",))
    async def list_regions(self) -> list[dict[str, str]]:
        return [{"code": "eu", "name": "Europe"}]

class Demo(a2kit.App):
    name = "demo"
    routers = (RegionsRouter,)

app = Demo()
VIEW = "ui://demo/dashboard.html"

# The UI SHELL — declares the ui:// resource the host renders. Presentation
# only; MCP-pinned by construction.
@app.mcp.tool(app={"resourceUri": VIEW})
async def dashboard() -> dict[str, str]:
    return {"open": VIEW}

# The UI BUNDLE — returned verbatim; a2kit constructs no UI bytes. CSP
# whitelists any external origin the iframe loads.
@app.mcp.resource(uri=VIEW, app={"csp": {"connectDomains": []}})
async def dashboard_view() -> str:
    return "<!doctype html><h1>Regions</h1><script>/* bundle */</script>"
```

A tool with `app=...` emits `_meta.ui.resourceUri`; a `ui://` resource is served
with MIME `text/html;profile=mcp-app`. The `app=` payload may be a FastMCP
`AppConfig`, an equivalent camelCase dict (shown above), or `True`.

## The division of labor

| Piece | Decorator | Surface | Pipeline |
|-------|-----------|---------|----------|
| UI shell | `@app.mcp.tool(app=...)` | MCP only | bypassed (presentation) |
| UI bundle | `@app.mcp.resource(uri="ui://...", app=...)` | MCP only | bypassed (bytes) |
| Data verbs | `@a2kit.read` / `@a2kit.write(surfaces=("mcp",))` | any | full (auth + format) |

MCP Apps interactivity decomposes into ordinary `tools/call` invocations, so the
iframe's callbacks are just your existing data verbs. **Put `authorize=` on the
data verbs**, not the shell — auth gates the data even when the shell is open.
(`authorize=` *is* still enforced on `@app.mcp.*` itself, at registration time,
so the hatch is never an auth gap.)

## Custom HTML or Prefab — your choice, mixed per tool

a2kit binds to the *standard*, never to a UI framework. Hand-written HTML (above)
and Prefab both forward through the same seam:

```python
@app.mcp.tool(app=True)        # Prefab's trigger; needs a consumer-installed prefab-ui
async def prefab_dash(): ...   # returns a PrefabApp
```

a2kit imports neither React nor `prefab` — it only forwards `app=` and serves the
bytes your resource function returns.

## Testing: the wire, not the pixels

Assert the `ui://` resource's wire shape — `_meta.ui.resourceUri`, the
`text/html;profile=mcp-app` MIME, the CSP — exactly as a2kit tests its other wire
formats. Rendering belongs to the host; smoke a real render against the
`ext-apps` `basic-host` or MCPJam outside CI.

A runnable example lives at [`examples/mcp_app/`](../../examples/mcp_app/server.py).

## What a2kit does not do

a2kit ships the projection *mechanism*; it never builds, bundles, or renders UI.
There is no typed `UIResource` return type today — the shell-vs-data split makes
one unnecessary (the data is always a separate verb). See ADR 0031 for the
deferred trigger.
