# a2kit

**Status:** v0.16.0 — coverage refill + `ConnectionConfig` rename.
`Annotated[T, Depends(factory)]` is the only supported DI shape:
`a2kit.contrib.connections.get_conn_factory(app, ConnT)` returns a
factory you wire into your tool kwonly via `Annotated[ConnT, Depends(get_conn)]`.
The fat tool decorator assembles an implicit Starlette-style middleware
chain at decoration time (`tool_call_guard` → `capability_guard` →
`otel_span` always; `write_enforce` / `list_view_apply` / `enrich_errors`
when the verb / Router / connection asks).

`ConnectionInfo` was renamed to `ConnectionConfig` in v0.16. The old name
is kept as a module-level alias for one cycle (removed in v0.17). All
v0.7-v0.12 connection-DI surfaces (`connection_param=`, `*, info: ConnT`
autodetect, `Router.store=`, `MCPRunner.store=`, `Plugin`/`PluginBase`)
were removed in v0.15.

See [CHANGELOG](CHANGELOG.md) for the full migration recipe.

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
| `App` (composition root: `connect()` / `use()` / `run()`) | `a2kit.app` |
| `ConnectionConfig` / `ConnectionStore` (atomic save, `${ENV}`/`op://` resolution, NamedTuple keys) | `a2kit.connections` |
| `Depends`, `DependsCycleError` (Annotated/Depends DI markers) | `a2kit.di` |
| `get_conn_factory(app, ConnT)` (canonical connection-injection factory) | `a2kit.contrib.connections` |
| `resolve_token` / `ResolverRegistry` (pluggable token resolvers, lazy at access time) | `a2kit.tokens` |
| **Fat** `@a2kit.tool(...)` (Annotated/Depends DI, list-view triad, tool-call guard, OTel, streaming) | `a2kit.tools` |
| `@a2kit.read` / `@a2kit.write` / `@a2kit.list` (verb decorators) | `a2kit.tools` |
| `Router`, `RouterRegistry`, `MCPRunner`, `build_cli`, `register_ephemeral_connections`, `scope_filter` | `a2kit.scaffold` |
| `Cap`, `capabilities` (StrEnum capability registry + `--select` grammar via `sel()`) | `a2kit._capabilities`, `a2kit._select` |
| `EnricherFn`, `chain(*fns)`, `connection_enricher(store)` (callable enricher contract) | `a2kit.enrichers` |
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
import a2kit
from a2kit import ConnectionConfig, ConnectionStore, resolve_token

# No `key=` declared → cls.Key resolves to the built-in `_DefaultKey(name: str)`.
class AtlassianConfig(ConnectionConfig):
    url: str
    email: str
    token: str
    read_only: bool = True

store = ConnectionStore(config_dir, AtlassianConfig)
await store.save(AtlassianConfig(key=("prod",), url="...", email="...", token="${ATL}"))
# Load shapes — pick the most readable for your call site:
info = await store.load("prod")              # bare-string sugar (single field)
info = await store.load(name="prod")         # kwargs
info = await store.load(("prod",))           # tuple
real_token = resolve_token(info.token)       # raises EnvVarNotFound on missing
```

Multi-part keys declare a NamedTuple and pass it via `key=`:

```python
from typing import Literal, NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: Literal["dev", "staging", "prod"]   # ty rejects env="production"
    db: str

class WidgetConfig(ConnectionConfig, key=WidgetKey):
    base_url: str
    api_key: str

await store.load(WidgetKey(project="acme", env="prod", db="main"))  # typed instance — most explicit
await store.load(project="acme", env="prod", db="main")             # kwargs
await store.load(("acme", "prod", "main"))                          # tuple
await store.load("acme", "prod", "main")                            # positional
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

`a2kit.App` is the recommended composition root — it wires
`ConnectionStore`, `Router`, `RouterRegistry`, `MCPRunner`, and
`build_cli` together so you don't thread them by hand. Drop down to the
primitives directly when you want fine-grained control:

```python
import a2kit

cli = a2kit.scaffold.build_cli(store, name="a2example")

@cli.command("serve")
def serve():
    server = make_fastmcp_server()
    a2kit.scaffold.MCPRunner(server, connection_store=store).run()
```

`build_cli` returns a Click group with the standard
`login`/`logout`/`connections list`/`connections show`/`connections delete`
commands. `MCPRunner` parses `--register`, `--scope`, `--select`, `--http`
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

v0.15+ shape: build an `App`, register a `ConnectionConfig` subclass via
`app.connect(...)`, mint a `get_conn` factory via
`a2kit.contrib.connections.get_conn_factory(app, ConnT)`, declare each
tool kwonly as `Annotated[ConnT, Depends(get_conn)]`. The kit injects
`connection: str` on the agent-facing schema, the resolver looks up the
saved key, your tool body sees the resolved `ConnectionConfig` instance.

```python
import a2kit
from typing import Annotated, ClassVar
from a2kit import Cap, Capability, ConnectionConfig
from a2kit.contrib.connections import get_conn_factory
from a2kit.di import Depends


class WidgetConfig(ConnectionConfig):
    base_url: str
    api_key: str
    read_only: bool = True


app = a2kit.App("widgets")
app.connect(WidgetConfig)
get_conn = get_conn_factory(app, WidgetConfig)


class WidgetsRouter(a2kit.Router):
    capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}


@WidgetsRouter.read()
async def get_widget(
    *,
    conn: Annotated[WidgetConfig, Depends(get_conn)],
    widget_id: str,
) -> dict:
    """Fetch a widget."""
    return {"id": widget_id, "url": conn.base_url}


@WidgetsRouter.write(capabilities={Cap.DESTRUCTIVE})
async def update_widget(
    *,
    conn: Annotated[WidgetConfig, Depends(get_conn)],
    widget_id: str,
) -> dict:
    """Update a widget."""
    return {"id": widget_id, "updated": True}


app.use(WidgetsRouter)

if __name__ == "__main__":
    app.run()
```

The kit:
- Surfaces `connection: str` on the agent-facing schema (the agent picks
  `connection="prod"`).
- Walks the `Depends(get_conn)` chain, looks up the saved key in the
  registered store, resolves `${ENV}` / `op://` tokens on str fields.
- Hides the resolver factory's kwonly from the agent's schema; binds the
  resolved `ConnectionConfig` instance into the fn at call time.
- Enforces `read_only=True` on `@write` tools via the `WriteEnforce`
  middleware (raises `WriteNotAllowed`).

Tests override the resolver: `app.dependency_overrides[get_conn] = fake_get_conn`.

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
    *,
    conn: Annotated[JiraConfig, Depends(get_conn)],
    filter: str = "",        # noqa: A002 — agent-facing
    fields: list[str] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> Page[dict]:
    # Tool body compiles filter→JQL, cursor→startAt, fields→&fields=
    return Page(items=[...], next_cursor="upstream-cursor-token")

# Mix: upstream paginates, kit filters within the page.
@a2kit.tool(filter=Local, pagination=Passthrough)
async def list_threads(
    *,
    conn: Annotated[RedditConfig, Depends(get_conn)],
    limit: int = 50,
    cursor: str | None = None,
) -> Page[dict]:
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
@server.tool(name="get-widget-v2", description="Custom MCP-side metadata.")
@a2kit.tool()
async def get_widget(...): ...
```

`App.cli` is the unified Click group — `serve`, connection-management,
and one subcommand per registered tool — so manual `build_cli(...)`
wiring is rarely needed.

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
runner = a2kit.scaffold.MCPRunner(
    server,
    connection_store=store,
    default_select=selected,
)
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
3. **`ConnectionConfig.key` shape.** Tuple-only is uniform but verbose.
   Per-class factory methods stay the consumer's call.
4. **Snapshot harness on FastMCP internals.** `_tool_manager.list_tools()` is
   an underscore-prefixed attribute. Pinned at `mcp >= 1.0`. If FastMCP moves
   the path, `a2kit.testing._list_tools` is the single seam to update.

## Migration

See [CHANGELOG](CHANGELOG.md) for the per-release migration recipes.
Recent highlights:

- **v0.16:** `ConnectionInfo` renamed to `ConnectionConfig`. Old name
  kept as a module-level alias for one cycle (removed in v0.17). Update
  imports / class bases at your leisure.
- **v0.15 (breaking):** `connection_param=`, `*, info: ConnT`
  autodetect, `@MyRouter.read()` typed-info DI, `Router.store`,
  `MCPRunner.store=`, `Plugin` / `PluginBase` / `Provider` are all
  removed. Migrate to `Annotated[ConnT, Depends(get_conn)]` via
  `a2kit.contrib.connections.get_conn_factory(app, ConnT)`.
- **v0.13:** `Annotated[T, Depends(factory)]` introduced as the
  preferred DI shape. Implicit middleware chain assembled at decoration
  time (`tool_call_guard`, `capability_guard`, `otel_span` always;
  `write_enforce`, `list_view_apply`, `enrich_errors` opt-in).
