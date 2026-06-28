# mcp-apps Specification

## Purpose
TBD - created by archiving change add-mcp-apps-support. Update Purpose after archive.
## Requirements
### Requirement: MCP App UI resources project verbatim through `@app.mcp.*`

a2kit SHALL serve MCP App (`ext-apps`) UI resources through the existing
`@app.mcp.tool` / `@app.mcp.resource` family without a dedicated authoring
surface. The `app=` payload (a FastMCP `AppConfig`, an equivalent dict, or
`True`) SHALL be forwarded verbatim to FastMCP at registration. A tool that
declares `app=AppConfig(resourceUri="ui://...")` SHALL expose
`_meta.ui.resourceUri` on its wire metadata, and a resource registered at a
`ui://` URI SHALL be served with MIME `text/html;profile=mcp-app`.

#### Scenario: Tool declares a UI resource

- **GIVEN** `@app.mcp.tool(name="dash", app=AppConfig(resourceUri="ui://app/view.html"))`
- **WHEN** the server is built and the tool list is read
- **THEN** the `dash` tool's wire `meta` carries `ui.resourceUri == "ui://app/view.html"`

#### Scenario: UI resource is served with the MCP App MIME and CSP

- **GIVEN** `@app.mcp.resource(uri="ui://app/view.html", app=AppConfig(csp=ResourceCSP(connect_domains=["https://api.example.com"])))` returning an HTML string
- **WHEN** the resource is listed and read
- **THEN** its MIME type is `text/html;profile=mcp-app`
- **AND** its wire `meta` carries `ui.csp.connectDomains == ["https://api.example.com"]`
- **AND** reading it returns the author's HTML bytes unchanged

### Requirement: a2kit imports no UI framework

a2kit SHALL NOT import any UI framework (e.g. `prefab`) to support MCP Apps, and
SHALL NOT make one a runtime dependency. Custom-HTML and Prefab-backed tools
SHALL both be expressible by forwarding `app=` verbatim, so they may be mixed
per-tool with a2kit blind to the choice.

#### Scenario: Building and serving an MCP App pulls no UI framework

- **GIVEN** an app with a `ui://` shell tool and an HTML resource
- **WHEN** the MCP server is built
- **THEN** no UI framework module (e.g. `prefab`) is present in `sys.modules`

#### Scenario: The Prefab trigger forwards without a2kit coupling

- **GIVEN** `@app.mcp.tool(app=True)` (Prefab's opt-in trigger)
- **WHEN** the server is built and the tool list is read
- **THEN** the tool's wire `meta` carries the forwarded `ui` payload
- **AND** a2kit imports no Prefab module to achieve this

### Requirement: a2kit constructs no UI bytes

a2kit SHALL ship only the projection mechanism for MCP Apps; it SHALL NOT
generate, bundle, transform, or render UI bytes. The HTML/JS/CSS bundle served
by a `ui://` resource SHALL originate solely from the consumer's resource
function return value.

#### Scenario: Resource bytes are passed through unchanged

- **GIVEN** a `ui://` resource function returning a specific HTML string
- **WHEN** the resource is read through the built server
- **THEN** the returned content equals the author's string byte-for-byte

