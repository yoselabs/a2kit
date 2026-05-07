# a2kit

**Status:** v0.7.0 — idiomatic Python pass. `Cap` is `StrEnum`; the
`*, info: ConnT | None = None` kwarg shape is gone (use
`Router.context.info()` — the only path); param docs auto-inject at
decoration time; `ToolKwargs` is public for higher-order Router decorators;
`_RouterContext` is FQN-scoped (no cross-module collisions); A2K012 follows
`__init__.py` re-export chains; new advisory rule A2K013.

See [CHANGELOG](CHANGELOG.md#070--2026-05-07) for the full migration recipe.

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

## API surface (v0.2)

| Primitive | Module | Example |
|---|---|---|
| `ConnectionInfo` / `ConnectionStore` | `a2kit.connections` | [`examples/multi_field_key_style.py`](examples/multi_field_key_style.py), [`examples/flat_key_style.py`](examples/flat_key_style.py) |
| `resolve_token` / `ResolverRegistry` | `a2kit.tokens` | [`examples/multi_field_key_style.py`](examples/multi_field_key_style.py) |
| **Fat** `@a2kit.tool(...)` (connection lookup + token + write + tool-call guard + OTel + streaming) | `a2kit.tools` | [`examples/fat_tool.py`](examples/fat_tool.py) |
| `tools.tool` (legacy, == v0.1), `preserve_return_annotation`, `assert_clean_string` | `a2kit.tools` | [`examples/tool_decorator.py`](examples/tool_decorator.py) |
| `ErrorEnricher`, `EnricherRegistry`, `ConnectionNotFoundEnricher` | `a2kit.errors` | [`examples/error_enricher.py`](examples/error_enricher.py) |
| `MCPRunner`, `RouterRegistry`, `Router`, `build_cli`, `register_ephemeral_connections`, `scope_filter` | `a2kit.scaffold` | [`examples/runner.py`](examples/runner.py), [`examples/feature_modules.py`](examples/feature_modules.py), [`examples/scaffold_cli.py`](examples/scaffold_cli.py) |
| `truncate`, `toon_or_json`, `format_response(filter=, fields=)` | `a2kit.formatter` | [`examples/formatter.py`](examples/formatter.py), [`examples/projection.py`](examples/projection.py) |
| `filter_records`, `project_fields` (CEL projection) | `a2kit.projection` | [`examples/projection.py`](examples/projection.py), [`examples/cel_filter_tool.py`](examples/cel_filter_tool.py) |
| `connection_param_doc` | `a2kit.docs` | [`examples/fat_tool.py`](examples/fat_tool.py) |
| `snapshot_schemas`, `assert_schemas_match`, `cassette` + pytest fixtures | `a2kit.testing`, `a2kit.pytest_plugin` | [`examples/schema_snapshot.py`](examples/schema_snapshot.py), [`examples/cassette_test.py`](examples/cassette_test.py) |
| `WriteNotAllowed`, `ToolCallContamination` (new exceptions) | `a2kit.exceptions` | — |

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

### `a2kit.errors`

```python
import a2kit

class _MyEnricher:
    def enrich(self, exc, *, tool_name=None):
        if isinstance(exc, KeyError):
            return RuntimeError(f"Not found: {exc.args[0]} (tool: {tool_name})")
        return exc

registry = a2kit.EnricherRegistry()
registry.register(a2kit.ConnectionNotFoundEnricher(store))
registry.register(_MyEnricher())
```

`ErrorEnricher` is a Protocol — any class with
`enrich(exc, *, tool_name) -> Exception` satisfies it. The registry runs
enrichers in registration order; first divergent return wins.

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

## How a new MCP starts here (v0.7)

v0.7 minimum: subclass `Router`, decorate tools with `@MyRouter.read/.write`,
read the resolved connection via `MyRouter.context.info()`. Plain docstrings —
the `connection:` line is auto-injected at decoration time.

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

### Filtering responses (the three tiers)

Pick the highest tier that fits — the lower tiers are escape hatches.

1. **Decorator kwargs** (primary path): pass `cel_filter_param=` /
   `fields_param=` on `@WidgetsRouter.read(...)` / `@a2kit.tool(...)`. The
   decorator threads the matching function args into `format_response` and
   returns the formatted envelope.
2. **`format_response(data, filter=..., fields=...)`** — call directly when
   you want the formatting envelope but not the auto-threading.
3. **`a2kit.projection.filter_records(records, expr=...)` /
   `project_fields(records, fields=...)`** — low-level escape hatch. Use only
   when you need raw record lists without the formatter envelope. See
   `examples/projection.py`.

The canonical example is `examples/cel_filter_tool.py` (decorator path);
`examples/projection.py` is for advanced shaping.

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

`ToolKwargs` is the public `TypedDict` mirror of `@a2kit.tool(...)`. See
`examples/higher_order_decorator.py`.

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

### LOC saved per tool (v0.2 → v0.3)

```python
# v0.2 — 2 decorators per tool, plus class repetition in MCPRunner/build_cli
@server.tool()
@a2kit.tool(store=store, connection_param="connection")
async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
    return {"id": widget_id, "url": info.base_url}

# v0.3 — 1 decorator
@a2kit.tool(server=server, store=store, connection_param="connection")
async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
    return {"id": widget_id, "url": info.base_url}
```

**Per-tool savings (decorator):** v0.2 = 2 lines; v0.3 = 1 line. **Saved
per tool: 1 decorator line.** A 30-tool MCP saves ~30 lines.

**Per-MCP savings (entrypoint):** dropping `connection_class=` from
`MCPRunner(...)` and `build_cli(...)` removes 2 redundant references to the
connection class. The default `cls.Key` is `_DefaultKey(name: str)`, so
single-key MCPs need no `key=` argument either.

Cumulatively against v0.2: ~35 LOC saved on a 30-tool MCP, plus the
removal of the parallel `KEY_PARTS` / `connection_class=` plumbing.

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
make examples    # all examples run end-to-end (multi_field_key_style,
                 # flat_key_style, tool_decorator, error_enricher,
                 # scaffold_cli --help, schema_snapshot, fat_tool, runner,
                 # formatter, feature_modules, streaming_tool, cassette_test)
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

## Migration sketch (existing MCPs)

Same as the 0.0.1 spike, plus:

- Replace each MCP's bespoke `mcp_tool` decorator with
  `@a2kit.tools.tool(enricher=...)`.
- Subclass `a2kit.errors.ErrorEnricher` for domain enrichers (e.g.
  column-not-found from a SQL-wrapping MCP, JQL-field-suggestions from a
  Jira/Confluence wrapper); register with a single `EnricherRegistry`.
- Replace `_parse_register_args` / `_parse_scope_args` with
  `a2kit.scaffold.register_ephemeral_connections` and
  `a2kit.scaffold.scope_filter`.
- Add a schema-snapshot test per MCP — closes the dev-quality / token-budget
  gap.

These changes are additive on the migration path; nothing here forces a re-do
of existing connection-store work.
