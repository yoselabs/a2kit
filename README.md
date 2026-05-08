# a2kit

**Status:** v0.13.0 — library-swap turn + middleware split.
`Annotated[T, Depends(factory)]` is the recommended DI shape (FastAPI /
FastMCP idiom; per-call cache, cycle detection, `app.dependency_overrides`
for tests). The fat tool decorator now assembles an implicit Starlette-style
middleware chain at decoration time (`tool_call_guard` → `capability_guard`
→ `otel_span` always; `write_enforce` / `list_view_apply` / `enrich_errors`
when the verb / Router / connection asks). Connection-aware helpers move
into `a2kit.contrib.connections`; `RunnerOptions` replaces argv-string
round-tripping in `App.cli`. Three bespoke modules retired in favour of
`anyio.from_thread.run`, `opentelemetry.trace.NoOpTracer`, and `vcrpy`
direct.

The v0.12 surfaces (`@Router.read()` / `@Router.write()`,
`*, info: TodoConn` auto-injection, `Router.store`, `MCPRunner.store=`)
are still present as compat — full deletion lands in v0.14 once the test
corpus migrates.

See [CHANGELOG](CHANGELOG.md#0130--2026-05-08) for the full migration recipe.

A thin library on top of FastMCP. Ships the primitives that recur across every
production MCP we've shipped: a `ConnectionStore`, lazy `${ENV_VAR}` / `op://`
token resolution, a fat tool decorator (connection lookup + token resolution +
write enforcement + tool-call guard + OTel + streaming), an `ErrorEnricher` cascade,
an `MCPRunner` for flag parsing + transport selection, a `RouterRegistry` for
auto-tagged tool capabilities + the `--select` grammar, TOON/JSON formatting +
recursive truncation, a JSON-schema snapshot harness, and a vcrpy-backed
cassette helper.

See [`ANTIPATTERNS.md`](ANTIPATTERNS.md) for the 13 concrete failures this
library exists to absorb.

**Foundation:** Python 3.11+ / FastMCP / uv / Pydantic v2 / pytest.

## What this lib is and isn't

**Is:**

- **Additive.** FastMCP stays first-class. Every primitive is opt-in; you can
  drop down to raw FastMCP at any boundary and nothing breaks.
- **Orthogonal.** No primitive overlaps a FastMCP primitive. Where they would,
  a2kit doesn't ship one.
- **Composable.** `@server.tool()` and `@a2kit.tools.tool(...)` stack cleanly,
  in either order.

**Isn't:**

- Not a FastMCP wrapper. There's no `a2kit.Server` or `a2kit.run()`.
- Not a "framework". No required base classes, no plugin system. You import the
  pieces you want.
- Not a vs-FastMCP story. If a primitive feels like it's competing with FastMCP,
  we've cut it.

## Install

```bash
cd ~/Workspaces/a2kit
make bootstrap
```

Requires Python 3.11+ and `uv`.

## Examples — what a real MCP looks like

The `examples/` folder is curated to five sequential files that mirror the shape
of the real MCPs this lib serves (`a2db`, `a2atlassian`, `a2web`):

| # | File | Demonstrates |
|---|---|---|
| 01 | [`01_minimal_mcp.py`](examples/01_minimal_mcp.py) | Smallest viable MCP — single `Router`, one read tool, one write tool, `build_cli` for `login`/`logout`/`serve`. The canonical shape. |
| 02 | [`02_multi_router_mcp.py`](examples/02_multi_router_mcp.py) | Multiple `Router`s + the `--select` grammar — pick which subset of tools the agent sees at runtime. |
| 03 | [`03_list_view.py`](examples/03_list_view.py) | List-view triad: `filter`/`fields`/`pagination` × `Local`/`Passthrough`. Demonstrates kit-handled CEL + projection alongside upstream-pushdown queries. |
| 04 | [`04_error_enricher.py`](examples/04_error_enricher.py) | Callable enrichers + `chain(*fns)` + `connection_enricher(store)` factory. |
| 05 | [`05_testing_patterns.py`](examples/05_testing_patterns.py) | Schema snapshots (drift gate + token-budget proxy) + vcrpy cassettes. |

## API surface

| Primitive | Module |
|---|---|
| `ConnectionInfo` / `ConnectionStore` (atomic save, `${ENV}`/`op://` resolution, NamedTuple keys) | `a2kit.connections` |
| `resolve_token` / `ResolverRegistry` (pluggable token resolvers, lazy at access time) | `a2kit.tokens` |
| **Fat** `@a2kit.tool(...)` (typed-info DI, connection auto-inject, list-view triad, tool-call guard, OTel, streaming) | `a2kit.tools` |
| `Router`, `RouterRegistry`, `MCPRunner`, `build_cli`, `register_ephemeral_connections`, `scope_filter` | `a2kit.scaffold` |
| `Cap`, `capabilities` (StrEnum capability registry + `--select` grammar via `sel()`) | `a2kit._capabilities`, `a2kit._select` |
| `EnricherFn`, `chain(*fns)`, `connection_enricher(store)` (callable enricher contract) | `a2kit.enrichers` (v0.11; `a2kit.errors` is a deprecation shim → removed in v0.13) |
| `ConnectionInfoLike`, `ConnectionStoreLike` (Protocols for duck-typed stores) | `a2kit.connections` |
| `FastMCPLike` (Protocol — minimum FastMCP server surface a2kit drives) | `a2kit.scaffold` |
| `ToolMetadata`, `tool_metadata(fn)` (read-only view of `@a2kit.tool` stamps) | `a2kit.tools` |
| `Response`, `Page[T]`, `Local`, `Passthrough`, `ListViewMode`, `format_response`, `toon_or_json`, `truncate` | `a2kit.formatter` |
| `filter_records`, `project_fields` (CEL projection, low-level) | `a2kit.projection` |
| `snapshot_schemas`, `assert_schemas_match`, `cassette` + pytest fixtures | `a2kit.testing`, `a2kit.pytest_plugin` |
| `ToolKwargs` TypedDict (for `Unpack[ToolKwargs]` higher-order decorators) | `a2kit._tool_kwargs` (re-exported as `a2kit.ToolKwargs`) |
| Exceptions: `WriteNotAllowed`, `ToolCallContamination`, `ConnectionNotFound`, `EnvVarNotFound`, … | `a2kit.exceptions` |

Optional extras: `a2kit[otel]` (opentelemetry-api), `a2kit[testing]` (vcrpy),
`a2kit[projection]` (cel-python).
Both are lazy-imported; the minimal install runs without either.

### `a2kit.connections`

```python
from a2kit import ConnectionInfo, ConnectionStore, resolve_token

# No `key=` declared → cls.Key resolves to the built-in `_DefaultKey(name: str)`.
class AtlassianInfo(ConnectionInfo):
    url: str
    email: str
    token: str
    read_only: bool = True

store = ConnectionStore(config_dir, AtlassianInfo)
store.save(AtlassianInfo(key=("prod",), url="...", email="...", token="${ATL}"))
# Load shapes — pick the most readable for your call site:
info = store.load("prod")              # bare-string sugar (single field)
info = store.load(name="prod")         # kwargs
info = store.load(("prod",))           # tuple
real_token = resolve_token(info.token)   # raises EnvVarNotFound on missing
```

Multi-part keys declare a NamedTuple and pass it via `key=`:

```python
from typing import Literal, NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: Literal["dev", "staging", "prod"]   # ty rejects env="production"
    db: str

class WidgetConn(ConnectionInfo, key=WidgetKey):
    base_url: str
    api_key: str

store.load(WidgetKey(project="acme", env="prod", db="main"))  # typed instance — most explicit
store.load(project="acme", env="prod", db="main")             # kwargs
store.load(("acme", "prod", "main"))                          # tuple
store.load("acme", "prod", "main")                            # positional
```

Atomic save (tempfile + chmod 0600 + rename), `A2KIT_CONFIG_HOME` env override,
typed exceptions on resolver failure (`KeyFieldMissing`, `KeyArityMismatch`).

### `a2kit.tools.tool`

```python
from mcp.server.fastmcp import FastMCP
import a2kit

server = FastMCP("widgets")

@server.tool()
@a2kit.tools.tool(enricher=my_enricher)
async def get_widget(widget_id: str) -> dict:
    """Always return dict — never str."""
    return {"id": widget_id}
```

- Refuses `-> str` returns at decoration time (`InvalidToolReturnTypeError`),
  catching the FastMCP double-serialisation bug class.
- Mirrors the return annotation onto the wrapper so FastMCP's
  `follow_wrapped=True` introspection sees the right shape (exposed as
  `preserve_return_annotation` for use without our decorator).
- Routes exceptions through the optional `enricher`. Without one, exceptions
  pass through unchanged.

### `a2kit.enrichers` (was `a2kit.errors` until v0.10)

```python
import a2kit

def my_enricher(exc, tool_name=None):
    if isinstance(exc, KeyError):
        return RuntimeError(f"Not found: {exc.args[0]} (tool: {tool_name})")
    return exc

# Compose with chain(...). connection_enricher(store) is the built-in factory.
combined = a2kit.chain(my_enricher, a2kit.connection_enricher(store))

@a2kit.tool(enricher=combined)
async def query(...): ...
```

An enricher is just a callable: `(exc, tool_name) -> exc`. Returning the
same object means no enrichment was applied. `chain(*fns)` runs each in
order; the first that transforms wins. No Protocol, no Registry, no class
hierarchy.

### `a2kit.scaffold`

```python
import a2kit

cli = a2kit.scaffold.build_cli(store, name="a2example")

@cli.command("serve")
def serve():
    server = make_fastmcp_server(store)
    a2kit.scaffold.MCPRunner(server, store=store).run()
```

`build_cli` returns a Click group with the standard
`login`/`logout`/`connections list`/`connections show`/`connections delete`
commands. The MCP author adds `serve` (or anything else) themselves; a2kit owns
no `main()`. `MCPRunner` parses `--register`, `--scope`, `--select`, `--http`
out of argv and dispatches the right transport.

### `a2kit.testing`

```python
import a2kit

paths = a2kit.testing.snapshot_schemas(server, snapshot_dir)
# Each file is compact JSON — `path.stat().st_size` is the per-tool token budget.

a2kit.testing.assert_schemas_match(server, snapshot_dir)
# raises SchemaSnapshotMismatch with unified diff on drift
```

Pytest integration (opt in via `conftest.py`):

```python
# tests/conftest.py
pytest_plugins = ["a2kit.pytest_plugin"]
```

```python
def test_schemas(schema_snapshot, tmp_path):
    schema_snapshot(my_server, tmp_path / "snapshots")
```

First run writes; subsequent runs assert. `pytest --update-schema-snapshots`
forces a rewrite.

**Why opt-in?** Auto-registering as a `pytest11` entry point would import
`a2kit.pytest_plugin` before pytest-cov starts measurement, which eagerly
imports the rest of the package and zeroes out import-time coverage. Opt-in
via `pytest_plugins` in your `conftest.py` is one line and avoids the trap.

## How a new MCP starts here

v0.9 shape: subclass `Router`, decorate tools with `@MyRouter.read/.write`,
declare a typed `info: <ConnectionInfo>` parameter, return data. Zero
connection plumbing.

```python
import a2kit
from typing import ClassVar
from a2kit import Cap, Capability

class WidgetConn(a2kit.ConnectionInfo):
    base_url: str
    api_key: str
    read_only: bool = True

class WidgetsRouter(a2kit.Router):
    capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}

@WidgetsRouter.read()                                # zero kwargs
async def get_widget(info: WidgetConn, widget_id: str) -> dict:
    """Fetch a widget."""
    return {"id": widget_id, "url": info.base_url}

@WidgetsRouter.write()
async def update_widget(info: WidgetConn, widget_id: str) -> dict:
    """Update a widget."""
    return {"id": widget_id, "updated": True}
```

The kit:
- Injects `connection: str` into the agent-facing schema (the agent picks
  `connection="prod"`).
- Looks up the saved key in the store, resolves `${ENV}` tokens.
- Enforces `read_only=True` on `.write()` tools (raises `WriteNotAllowed`).
- Hides the typed `info` param from the agent's schema; binds the resolved
  `ConnectionInfo` instance into the fn at call time.

`Router.context.info()` survives as the helper-function escape hatch (call
sites that aren't the tool itself).

```python
# my_mcp/server.py
import a2kit
from a2kit import Cap, Router
from mcp.server.fastmcp import FastMCP


class WidgetConn(a2kit.ConnectionInfo):
    base_url: str
    api_key: str
    read_only: bool = True


class WidgetsRouter(Router):
    pass  # name auto-derives to "widgets"


@WidgetsRouter.read(connection_param="connection")
async def get_widget(connection: str, widget_id: str) -> dict:
    """Fetch a widget."""  # connection_param_doc auto-prepended
    info = WidgetsRouter.context.info()
    return {"id": widget_id, "url": info.base_url}


@WidgetsRouter.write(connection_param="connection", capabilities={Cap.DESTRUCTIVE})
async def update_widget(connection: str, widget_id: str) -> dict:
    """Update a widget."""
    return {"id": widget_id, "updated": True}


store = a2kit.ConnectionStore(a2kit.default_config_dir(), WidgetConn)
server = FastMCP("widgets")
routers = a2kit.RouterRegistry()
routers.add(WidgetsRouter(store=store))

if __name__ == "__main__":
    a2kit.MCPRunner(server, store=store, router_registry=routers).run()
```

### List-view tools (filter / fields / pagination)

Three orthogonal concerns, two execution modes each. Pick `Local` (kit
handles) or `Passthrough` (tool handles).

```python
from a2kit import Local, Page, Passthrough

# Kit handles all three — works for in-memory data, Reddit JSON, etc.
@a2kit.tool(filter=Local, fields=Local, pagination=Local)
def list_widgets() -> list[dict]:
    return _ALL_WIDGETS

# Tool handles all three — for upstreams with their own query language.
@a2kit.tool(filter=Passthrough, fields=Passthrough, pagination=Passthrough)
async def list_issues(
    info: JiraConn,
    filter: str = "",        # noqa: A002 — agent-facing
    fields: list[str] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> Page[dict]:
    # Tool body compiles filter→JQL, cursor→startAt, fields→&fields=
    return Page(items=[...], next_cursor="upstream-cursor-token")

# Mix: upstream paginates, kit filters within the page.
@a2kit.tool(filter=Local, pagination=Passthrough)
async def list_threads(info: RedditConn, limit: int = 50, cursor: str | None = None) -> Page[dict]:
    return Page(items=await reddit.fetch(after=cursor), next_cursor=...)
```

Result is wrapped in `Response(format='tsv'|'toon'|'json', data, truncated, next_cursor)`
whenever any list-view mode is set. See `examples/03_list_view.py`.

For ad-hoc / non-tool use:
- **`format_response(data, filter=..., fields=...)`** — call directly.
- **`a2kit.projection.filter_records` / `project_fields`** — raw, no envelope.

### Higher-order decorators (`Unpack[ToolKwargs]`)

Build a custom Router classmethod factory whose kwargs stay type-checked:

```python
from typing import Unpack
import a2kit
from a2kit import Cap, ToolKwargs


class MetricsRouter(a2kit.Router):
    @classmethod
    def expensive(cls, **kwargs: Unpack[ToolKwargs]):
        existing = set(kwargs.get("capabilities", set()) or set())
        kwargs["capabilities"] = existing | {Cap.EXPENSIVE}
        return cls.tool(**kwargs)


@MetricsRouter.expensive()
async def heavy_query(scope: str) -> dict:
    return {"scope": scope}
```

`ToolKwargs` is the public `TypedDict` mirror of `@a2kit.tool(...)`. As of
v0.8, `Router.tool/.read/.write` use `Unpack[ToolKwargs]` themselves — your
classmethod factory inherits the same type-checked kwarg contract.

Run it with the default safe selection (read-only, non-destructive):

```bash
my-mcp                                        # → --select "default and not write and not destructive"
my-mcp --select "widgets and (read or write)" # opt into writes
my-mcp --select "router:widgets and not destructive"
```

If you need explicit FastMCP options (custom `name=`, `description=`), the
two-decorator stack still works:

```python
@a2kit.tool(store=store, connection_param="connection")
@server.tool(name="get-widget-v2", description="Custom MCP-side metadata.")
async def get_widget(...): ...
```

The CLI side stays one line:

```python
# my_mcp/cli.py
import a2kit
from .server import store

cli = a2kit.scaffold.build_cli(store, name="a2widgets")
if __name__ == "__main__":
    cli()
```

## Capabilities (v0.3.1)

Tools carry a set of capability tags. Tags drive the `--select` grammar.

**Built-ins** (importable as `a2kit.Cap`):

| Constant | Tag | Auto-applied by |
|---|---|---|
| `Cap.READ` | `read` | `Router.register_read` |
| `Cap.WRITE` | `write` | `Router.register_write` or `@a2kit.tool(write=True)` |
| `Cap.DESTRUCTIVE` | `destructive` | author |
| `Cap.EXPENSIVE` | `expensive` | author |
| `Cap.PII` | `pii` | author |
| `Cap.EXTERNAL` | `external` | author |

**Custom caps** (register at app startup):

```python
a2kit.capabilities.register("tickets-management", description="Ticket flows that may modify upstream state.")
```

**Author-tagging on a tool:**

```python
@a2kit.tool(capabilities={Cap.PII, "tickets-management"})
async def export_tickets(...) -> dict: ...
```

**`--select` grammar** (CLI + typed builder):

- Atoms: bare names — `issues`, `read`, `purge`.
- Optional namespace: `tool:purge`, `router:issues`, `cap:write`.
- Operators: `and`, `or`, `not`, parentheses.
- Default expression: `default and not write and not destructive`. Override
  per project via `[tool.a2kit.runner] default_select = "..."`.

```python
# CLI: my-mcp --select "default and not destructive"
# In code:
from a2kit import sel, Cap
selected = sel("issues") & ~sel(Cap.DESTRUCTIVE)
runner = a2kit.scaffold.MCPRunner(server, store=store, default_select=selected)
```

## Lint and runtime checks (v0.3.1)

```bash
uvx a2kit lint src/ tests/ examples/
uvx a2kit check --import my_mcp.server:server --snapshot-dir __snapshots__
```

Six static rules (`A2K001`..`A2K006`) and four runtime checks
(`A2KR001`..`A2KR004`). Configure via `[tool.a2kit.lint]` /
`[tool.a2kit.check]` in `pyproject.toml`. Per-line ignores via
`# noqa: A2K001`. Full reference in [`LINT.md`](LINT.md).

## Quality gates

```bash
make check       # ruff check + ruff format --check + pytest (100% line+branch coverage)
make examples    # all 5 curated examples run end-to-end
```

See [`ANTIPATTERNS.md`](ANTIPATTERNS.md) for the consolidated anti-pattern
list (FastMCP frictions, primitive-design traps, OTel/streaming gotchas).

## Open questions

1. **Resolver registry: global vs per-store?** Default registry is
   module-global; `resolve_token(..., registry=...)` accepts an explicit
   instance. Per-store registries make sense when a single agent process needs
   different resolution policies per MCP.
2. **Frozen-with-update vs strict-frozen?** Pydantic `model_copy(update=...)`
   works on frozen models. Convention pending until a third consumer chooses.
3. **`ConnectionInfo.key` shape.** Tuple-only is uniform but verbose.
   Per-class factory methods stay the consumer's call.
4. **Snapshot harness on FastMCP internals.** `_tool_manager.list_tools()` is
   an underscore-prefixed attribute. Pinned at `mcp >= 1.0`. If FastMCP moves
   the path, `a2kit.testing._list_tools` is the single seam to update.

## Migration to v0.9 from earlier versions

**v0.8 → v0.9:**

- `@MyRouter.read(connection_param="conn") + def fn(conn: str)` → `@MyRouter.read() + def fn(info: WidgetConn)`.
  Drop the `connection_param=` kwarg, replace the `conn: str` arg with a typed
  `info: <ConnectionInfo subclass>` arg. Kit injects `connection: str` for
  the agent and binds the resolved info into your typed param.
- `@a2kit.tool(projection=True)` → `@a2kit.tool(filter=Local, fields=Local)`
  (Local mode = same v0.8 behaviour). For upstream-pushdown, use `Passthrough`.
- `@a2kit.tool(cel_filter_param="filter", fields_param="fields")` →
  `@a2kit.tool(filter=Local, fields=Local)`. The `_param=` kwargs are gone.
- `IssuesRouter(capabilities={Cap.EXTERNAL})` → `class IssuesRouter(Router): capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}`.
- `EnricherRegistry()` + `.register(...)` + `ErrorEnricher` Protocol →
  callable functions composed with `chain(*fns)`.
- `ConnectionNotFoundEnricher(store)` → `connection_enricher(store)` (factory
  returning a closure).
- `Response.format == "toon"` on flat data is now `"tsv"`. Nested-cell rows
  remain `"toon"`.

**v0.7 → v0.8 (still applies):**

- `xml_guard=` → `tool_call_guard=`. `ToolXMLContamination` →
  `ToolCallContamination`. `format_response(...)["format"]` →
  `format_response(...).format`. `@a2kit.tool(ephemeral=...)` →
  `Router(..., ephemeral={...})`.
