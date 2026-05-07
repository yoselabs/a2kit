# a2kit

**Status:** v0.2 — production-grade primitive set.

A thin library on top of FastMCP. Ships the primitives that recur across every
production MCP we've shipped: a `ConnectionStore`, lazy `${ENV_VAR}` / `op://`
token resolution, a fat tool decorator (connection lookup + token resolution +
write enforcement + xml guard + OTel + streaming), an `ErrorEnricher` cascade,
an `MCPRunner` for flag parsing + transport selection, a `FeatureRegistry` for
`--enable`, TOON/JSON formatting + recursive truncation, a JSON-schema snapshot
harness, and a vcrpy-backed cassette helper.

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
| `ConnectionInfo` / `ConnectionStore` | `a2kit.connections` | [`examples/a2db_style.py`](examples/a2db_style.py), [`examples/a2atlassian_style.py`](examples/a2atlassian_style.py) |
| `resolve_token` / `ResolverRegistry` | `a2kit.tokens` | [`examples/a2db_style.py`](examples/a2db_style.py) |
| **Fat** `@a2kit.tool(...)` (connection lookup + token + write + xml + OTel + streaming) | `a2kit.tools` | [`examples/fat_tool.py`](examples/fat_tool.py) |
| `tools.tool` (legacy, == v0.1), `preserve_return_annotation`, `assert_clean_string` | `a2kit.tools` | [`examples/tool_decorator.py`](examples/tool_decorator.py) |
| `ErrorEnricher`, `EnricherRegistry`, `ConnectionNotFoundEnricher` | `a2kit.errors` | [`examples/error_enricher.py`](examples/error_enricher.py) |
| `MCPRunner`, `FeatureRegistry`, `build_cli`, `register_ephemeral_connections`, `scope_filter` | `a2kit.scaffold` | [`examples/runner.py`](examples/runner.py), [`examples/feature_modules.py`](examples/feature_modules.py), [`examples/scaffold_cli.py`](examples/scaffold_cli.py) |
| `truncate`, `toon_or_json`, `format_response` | `a2kit.formatter` | [`examples/formatter.py`](examples/formatter.py) |
| `connection_param_doc` | `a2kit.docs` | [`examples/fat_tool.py`](examples/fat_tool.py) |
| `snapshot_schemas`, `assert_schemas_match`, `cassette` + pytest fixtures | `a2kit.testing`, `a2kit.pytest_plugin` | [`examples/schema_snapshot.py`](examples/schema_snapshot.py), [`examples/cassette_test.py`](examples/cassette_test.py) |
| `WriteNotAllowed`, `ToolXMLContamination` (new exceptions) | `a2kit.exceptions` | — |

Optional extras: `a2kit[otel]` (opentelemetry-api), `a2kit[testing]` (vcrpy).
Both are lazy-imported; the minimal install runs without either.

### `a2kit.connections`

```python
from a2kit import ConnectionInfo, ConnectionStore, resolve_token

class AtlassianInfo(ConnectionInfo):
    KEY_PARTS = 1   # or None for any arity
    url: str
    email: str
    token: str
    read_only: bool = True

store = ConnectionStore(config_dir, AtlassianInfo)
store.save(AtlassianInfo(key=("prod",), url="...", email="...", token="${ATL}"))
info = store.load(("prod",))
real_token = resolve_token(info.token)   # raises EnvVarNotFound on missing
```

Tuple keys generalise both a2db (3-part) and a2atlassian (1-part). Atomic save
(tempfile + chmod 0600 + rename), `A2KIT_CONFIG_HOME` env override, typed
exceptions on resolver failure.

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
  catching the a2db `4d07632` bug class.
- Mirrors the return annotation onto the wrapper so FastMCP's
  `follow_wrapped=True` introspection sees the right shape (the a2atlassian
  `decorators.py:84-85` trick, exposed as `preserve_return_annotation` for use
  without our decorator).
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
import click

cli = a2kit.scaffold.build_cli(store, connection_class=MyConn, name="a2example")

@cli.command("serve")
def serve():
    ephemeral = a2kit.scaffold.register_ephemeral_connections(sys.argv[1:], MyConn)
    server = make_fastmcp_server(store, ephemeral)
    server.run()
```

`build_cli` returns a Click group with the standard
`login`/`logout`/`connections list`/`connections show`/`connections delete`
commands. The MCP author adds `serve` (or anything else) themselves; a2kit owns
no `main()`.

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

## How a new MCP starts here (v0.2)

```python
# my_mcp/server.py
import a2kit
from mcp.server.fastmcp import FastMCP

class WidgetConn(a2kit.ConnectionInfo):
    KEY_PARTS = 1
    base_url: str
    api_key: str
    read_only: bool = True

store = a2kit.ConnectionStore(a2kit.default_config_dir(), WidgetConn)
enricher = a2kit.EnricherRegistry()
enricher.register(a2kit.ConnectionNotFoundEnricher(store))

server = FastMCP("widgets")

@server.tool()
@a2kit.tool(store=store, connection_param="connection", enricher=enricher)
async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
    f"""Fetch a widget. {a2kit.docs.connection_param_doc(cli="a2widgets")}"""
    return {"id": widget_id, "url": info.base_url}

@server.tool()
@a2kit.tool(store=store, connection_param="connection", write=True, enricher=enricher)
async def update_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
    return {"id": widget_id, "updated": True}

if __name__ == "__main__":
    a2kit.scaffold.MCPRunner(server, store=store, connection_class=WidgetConn).run()
```

The CLI side gets the standard commands for free:

```python
# my_mcp/cli.py
import a2kit
from .server import store, WidgetConn

cli = a2kit.scaffold.build_cli(store, connection_class=WidgetConn, name="a2widgets")
if __name__ == "__main__":
    cli()
```

### LOC saved per tool (v0.1 → v0.2)

A direct port of the v0.1 walkthrough's `get_widget`:

```python
# v0.1 — 4 lines of boilerplate inside the body
async def get_widget(connection: str, widget_id: str) -> dict:
    info = store.load((connection,)) if connection not in ephemeral else ephemeral[(connection,)]
    token = a2kit.resolve_token(info.api_key)
    return {"id": widget_id, "url": info.base_url}

# v0.2 — 0 lines of boilerplate; decorator does it
@a2kit.tool(store=store, connection_param="connection")
async def get_widget(connection: str, widget_id: str, *, info: WidgetConn | None = None) -> dict:
    return {"id": widget_id, "url": info.base_url}
```

**Body LOC:** v0.1 = 3 (load + resolve + return); v0.2 = 1 (return). **Saved
per tool: 2 lines.** A 30-tool MCP saves ~60 lines of repetitive
boilerplate, plus the v0.1 `if connection not in ephemeral` ternary that
neither MCP got right at first.

`MCPRunner` replaces ~40 lines of argv parsing in `mcp_server.py::main()`
(both reference MCPs hand-roll `_parse_register_args`,
`_parse_scope_args`, `_parse_enable_args` — see `ANTIPATTERNS.md` #6 for
why it's a helper not a `main()`).

## Quality gates

```bash
make check       # ruff check + ruff format --check + pytest (100% line+branch coverage)
make examples    # all examples run end-to-end (a2db_style, a2atlassian_style,
                 # tool_decorator, error_enricher, scaffold_cli --help,
                 # schema_snapshot, fat_tool, runner, formatter, feature_modules,
                 # streaming_tool, cassette_test)
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

## Migration sketch (a2db, a2atlassian)

Same as the 0.0.1 spike, plus:

- Replace each MCP's bespoke `mcp_tool` decorator with
  `@a2kit.tools.tool(enricher=...)`.
- Subclass `a2kit.errors.ErrorEnricher` for domain enrichers
  (column-not-found in a2db, JQL-field-suggestions in a2atlassian); register
  with a single `EnricherRegistry`.
- Replace `_parse_register_args` / `_parse_scope_args` with
  `a2kit.scaffold.register_ephemeral_connections` and
  `a2kit.scaffold.scope_filter`.
- Add a schema-snapshot test per MCP — closes the dev-quality / token-budget
  gap.

These changes are additive on the migration path; nothing here forces a re-do
of existing connection-store work.
