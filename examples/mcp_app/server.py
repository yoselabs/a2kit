"""MCP App (``ui://`` interactive UI) demo — the escape-hatch pattern.

a2kit serves MCP Apps (the ``ext-apps`` standard) through the existing
``@app.mcp.*`` family — no dedicated authoring surface, and a2kit imports no
UI framework. The division of labor (see ADR 0030):

- **UI shell** — ``@app.mcp.tool(app=AppConfig(resourceUri="ui://..."))``. It
  declares the UI resource; the host preloads + renders it in a sandboxed
  iframe. MCP-pinned presentation; it carries no business logic.
- **UI bundle** — ``@app.mcp.resource(uri="ui://...", app=AppConfig(...))``
  returns the HTML/JS/CSS string verbatim (a2kit constructs no UI bytes). CSP
  whitelists any external origins the iframe loads.
- **Data verbs** — ordinary projection verbs (``@a2kit.read`` /
  ``@a2kit.write``). The iframe calls these back over the MCP Apps bridge
  (``tools/call``), so they ride the full dispatch pipeline: ``authorize=``,
  ``Principal``, format-routing. Auth lives here, on the data, not on the
  presentation shell.

Custom HTML (shown here) and Prefab (``@app.mcp.tool(app=True)`` + a
consumer-installed ``prefab-ui``) both forward through the same seam and may be
mixed per-tool — a2kit stays blind to the choice.

Run::

    python -m examples.mcp_app.server serve        # MCP transport
"""

from __future__ import annotations

from pydantic import BaseModel

import a2kit


class Region(BaseModel):
    """One row the dashboard renders."""

    code: str
    name: str
    orders: int


class RegionsRouter(a2kit.Router):
    """The data the UI calls back for — a normal projection verb.

    Exposed on the MCP surface so the iframe can invoke it by canonical name
    (``regions_list_regions``). Because it is a projection verb it rides the
    full pipeline; add ``authorize=`` here to gate the *data* (the shell stays
    presentation).
    """

    slug = "regions"
    name = "regions"

    @a2kit.read(surfaces=("mcp",))
    async def list_regions(self) -> list[Region]:
        return [
            Region(code="eu", name="Europe", orders=1240),
            Region(code="na", name="North America", orders=2105),
            Region(code="apac", name="Asia-Pacific", orders=860),
        ]


class McpAppDemo(a2kit.App):
    name = "mcp-app-demo"
    routers = (RegionsRouter,)


app = McpAppDemo()

_VIEW_URI = "ui://mcp-app-demo/dashboard.html"

# A self-contained illustrative bundle. In a real app this would be a built
# React/Vue/vanilla bundle string; here it is inline HTML with a commented
# placeholder for the data callback. a2kit serves these bytes unchanged.
_DASHBOARD_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>Regions</title></head>
  <body>
    <h1>Regions dashboard</h1>
    <table id="regions"><thead><tr><th>Code</th><th>Name</th><th>Orders</th></tr></thead>
      <tbody></tbody></table>
    <script>
      // In an MCP Apps host, the iframe loads the ext-apps client SDK
      // (@modelcontextprotocol/ext-apps; `mcpApp` here is the ext-apps client,
      // NOT a2kit's app) and calls a2kit projection verbs back over the bridge
      // to fetch fresh data, e.g.:
      //   const res = await mcpApp.callServerTool({ name: "regions_list_regions" });
      //   mcpApp.ontoolresult = (r) => render(r.structuredContent.result);
      // The data verb runs the full a2kit pipeline (auth / format-routing).
      // See docs/patterns/mcp-apps.md → "Going further" for the bridge API
      // and starter bundles (React/Vue/vanilla) — that side is not a2kit's.
    </script>
  </body>
</html>
"""


@app.mcp.tool(app={"resourceUri": _VIEW_URI}, title="Open the regions dashboard")
async def regions_dashboard() -> dict[str, str]:
    """The UI shell: declares the ``ui://`` resource the host renders."""
    return {"open": _VIEW_URI}


@app.mcp.resource(
    uri=_VIEW_URI,
    app={"csp": {"connectDomains": []}},
    name="regions-dashboard-ui",
)
async def dashboard_view() -> str:
    """The UI bundle bytes — returned verbatim; a2kit constructs no UI."""
    return _DASHBOARD_HTML


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
