# a2kit

**Fat tool decorator on top of FastMCP — protocol-agnostic core, opt-in plugin packages.**

a2kit ships an `App`, verb decorators (`@a2kit.read` / `@a2kit.write` /
`@a2kit.list_`), and a `ToolContext` Protocol — that's it for the core.
Everything else (connections, formatter, select grammar, lint, testing
helpers, MCP server, CLI) lives under `a2kit.packages.*` as opt-in plugin
packages. FastMCP is a hard dependency, but it's confined to
`a2kit.packages.mcp` — `import a2kit` stays under 100 ms.

A single console script handles every mode — tool subcommands, connection
management, schema dump, and `serve`:

```python
# tracker/server.py
import a2kit
from a2kit.packages.connections import get_conn_factory

from .routers import ProjectsRouter, TasksRouter
from .connection import TrackerConn

app = a2kit.App("tracker")
app.connect(TrackerConn)
app.use(ProjectsRouter())
app.use(TasksRouter())

def main() -> None:
    a2kit.run(app)
```

```toml
[project.scripts]
tracker = "tracker.server:main"
```

```bash
tracker --help
tracker tasks list-tasks --project-id=abc      # in-process; no MCP roundtrip
tracker connections login tracker --field db_path=./data.jsonl
tracker schema list-tasks                       # TOON by default; --format=json opts in
tracker serve --transport=stdio                 # only this loads fastmcp
```

## Install

```bash
uv pip install --pre a2kit
```

`--pre` is required until [`toon-format`](https://pypi.org/project/toon-format/)
ships 1.0; a2kit pins the working pre-release exactly (`0.9.0b1`).

## API surface

### Core (`a2kit`)

| Symbol | Purpose |
|---|---|
| `a2kit.App(name)` | Composition root. `app.use(thing)` (polymorphic — Plugin / Router / class), `app.use_factory(factory, as_=stub)`, `app.set_ldd(...)`. |
| `a2kit.Router` | Subclass; decorate methods with `@a2kit.read/write/list_`. Class kwarg: `class TasksRouter(a2kit.Router, enricher=fn):`. Router applies enrichers when collecting tools. |
| `a2kit.Plugin` | Protocol for opt-in features. Plugins contribute CLI subcommands, MCP middleware, DI resolvers, and may claim foreign types passed to `app.use(...)`. |
| `a2kit.DependsResolver` | Protocol for plugin-contributed `Depends(<class>)` resolvers. |
| `a2kit.RouterRegistry` | Internal; collects `Router` instances. |
| `@a2kit.tool / read / write / list_` | Verb decorators. Map to `mcp.types.ToolAnnotations` + tags. |
| `a2kit.A2KitMeta` | Frozen typed contract stamped onto each tool fn (`fn._a2kit`). |
| `a2kit.ToolContext` | Protocol for protocol-neutral logging + progress. Both adapters supply an implementation. |
| `a2kit.Cap` | Built-in capability `StrEnum`. `a2kit.capabilities.register(...)` for custom tags. |
| `a2kit.run(app, argv=None)` | Single-entry CLI dispatch. Builds Click group, invokes. |

### Plugin packages (`a2kit.packages.*`)

| Package | Purpose |
|---|---|
| `a2kit.packages.mcp` | FastMCP adapter. `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. The ONE place fastmcp imports. |
| `a2kit.packages.cli` | Click adapter. `build_full_cli(app)` returns the progressive-disclosure CLI. |
| `a2kit.packages.connections` | `ConnectionConfig`, `ConnectionStore`, `get_conn_factory`. Pydantic-settings-backed; eager `${VAR}` / `op://` resolution. |
| `a2kit.packages.formatter` | TOON / JSON output normalization via `toon-format`. `format_response(raw, format_hint=...)`. |
| `a2kit.packages.select` | `compile`, `evaluate`, `validate_atoms` over real CEL syntax. |
| `a2kit.packages.enrichers` | Protocol-neutral `wrap(fn, enricher)` + `connection_enricher`. |
| `a2kit.packages.testing` | Thin pytest fixtures, syrupy `TOONSnapshotExtension`, `make_test_app(routers, overrides=...)`. |
| `a2kit.packages.lint` | Static + runtime A2K rules. `a2kit lint static <path>` / `a2kit lint runtime --import pkg:app`. |

### Dependency injection — class as the key

Three injection shapes; pick the one that reads cleanest at the call site.

```python
from uncalled_for import Depends
import a2kit

# 1. Connection class — `Depends(TrackerConn)` resolves via the registered loader.
async def get_project(
    *,
    conn: TrackerConn = Depends(TrackerConn),
    connection: str,
    project_id: str,
) -> Project: ...

# 2. Store class — runtime composes conn → store. Declare via `Store[ConnT]`.
class TrackerStore(a2kit.Store[TrackerConn]):
    def __init__(self, conn: TrackerConn) -> None: ...

async def archive_project(
    *,
    store: TrackerStore = Depends(TrackerStore),
    connection: str,
    project_id: str,
) -> Project: ...

# 3. Stub factory — for multi-tenant or test overrides where the factory
#    needs to be swapped at composition root. Backwards-compatible legacy path.
async def get_conn(*, connection: str) -> TrackerConn: ...
app.use_factory(my_factory, as_=get_conn)
```

The runtime hides class-Depends params from the tool's input schema — only
`connection: str` (and the user kwargs) appear to the agent.

a2kit re-exports zero external symbols. Users import `Depends` from
`uncalled_for` directly:

```python
from uncalled_for import Depends

class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(
        self, *, conn: TrackerConn = Depends(get_conn), task_id: str
    ) -> Task: ...
```

The `Annotated[T, Depends(...)]` form is **not** supported for value
injection — use parameter-default form. The `A2K-DI-ANNOTATED` lint rule
flags the misuse.

### Logging + progress + events + reports (`ToolContext`)

`ToolContext` exposes **four channels** for mid-flight communication.
Each emission carries an elapsed `+s.mmm` timestamp and reaches the
caller immediately (no buffering).

| Channel | API | When to use |
|---|---|---|
| Process telemetry | `ctx.info / warning / error / debug(msg, **kw)` | Free-form ambient logs |
| Numeric progress | `await ctx.report_progress(i, n)` | "30 of 100" — for progress bars |
| **Narrative events** | `await ctx.event(name, **payload)` | Typed milestones agents pattern-match (e.g. `"api.fetched"`) |
| **Typed reports** | `await ctx.report(payload)` (requires `report=ReportT` on decorator) | Mid-flight result chunks with a declared schema |

```python
from pydantic import BaseModel

class BatchReport(BaseModel):
    batch: int
    accepted: int

@a2kit.read(report=BatchReport)
async def bulk_import(*, ctx: a2kit.ToolContext, file: str) -> dict:
    await ctx.event("import.started", file=file)
    items = await load(file)
    for i, item in enumerate(items):
        await ctx.report_progress(i, len(items))
        await ctx.report(BatchReport(batch=i, accepted=1))
    await ctx.event("import.complete", count=len(items))
    return {"imported": len(items)}
```

**Wire format.** CLI: `[ +s.mmm LEVEL] msg key=val` lines on stderr.
MCP: `notifications/message` with `data.elapsed_ms: int` and (for events
/ reports) a `data.a2kit_kind` discriminator. Keep messages short
(≤ 60 char guideline) — long lines burn agent context tokens.

**Kill-switch.** Top-level CLI flags `--no-reports` / `--no-events` per
invocation; `app.set_ldd(reports=False, events=False)` programmatically;
env `A2KIT_LDD=off` process-wide. Most-specific layer wins. Disabled
emissions still type-validate `report=` payloads — keeps tests
deterministic.

**Lint rule.** `A2K-LDD-REPORT-TYPE` fires when `ctx.report(...)` is
called without `report=` declared on the decorator, or when the declared
type is defined inside a function (Pydantic forward-ref constraint).

The `ctx` parameter is stripped from the input schema and from CLI
option generation.

## CLI

`a2kit.run(app)` exposes:

- `<app> --help` — top-level: one entry per Router (with progressive-disclosure hint), plus `connections`, `schema`, `serve`.
- `<app> <router> --help` — list tools in that router.
- `<app> <router> <tool> [--name VALUE ...] [--format=auto|toon|json] [--schema]` — invoke the tool in-process. Output flows through the formatter.
- `<app> connections {login,logout,list,show,delete}` — manage saved connections.
- `<app> schema [TOOL] [--format=toon|json] [--jsonl]` — schema discovery.
- `<app> serve [--transport=stdio|http] [--host] [--port]` — MCP server (the ONLY mode that loads fastmcp).

`'fastmcp' not in sys.modules` after any non-`serve` command — verified by `tests/test_cold_start.py`.

## Connections

`ConnectionConfig` inherits `pydantic_settings.BaseSettings`. Substitution is
**eager**: `${VAR}` and `op://...` references resolve at `store.load(...)`,
not at first tool call. Missing env vars / unreachable secrets fail fast.

```python
from a2kit.packages.connections import ConnectionConfig

class TrackerConn(ConnectionConfig):
    db_path: str
    token: str = ""
    read_only: bool = False
```

Round-trip preserves placeholders: `store.save(cfg)` writes the original `${MY_TOKEN}` string, never the resolved value.

Cloud-secret backends (AWS / Azure / GCP) compose via pydantic-settings sources — no a2kit-specific resolver registration needed.

## Lint

```bash
a2kit lint static src/
a2kit lint runtime --import myapp.server:app
```

v1.0-relevant rules:

- `A2K-DI-ANNOTATED` — `Annotated[T, Depends(fn)]` is not supported.
- `A2K-DI-IMPORT-LEGACY` — `from a2kit.di import Depends`.
- `A2K-DI-IMPORT-SLOW` — `from fastmcp.dependencies import Depends`.
- `A2K-DI-KWONLY` — DI parameters must be keyword-only.
- `A2K-DI-PYDANTIC-VALIDATE` — `pydantic.validate_call` on a Depends-defaulted fn leaks the sentinel.
- `A2K-CONN-LIST-PLACEHOLDER` — `${VAR}` inside list/dict fields on `ConnectionConfig`.
- `A2K-IMPORT-DISCIPLINE` — `fastmcp` imports outside `packages/mcp/` and the lazy-load lines in `packages/cli/builder.py`.

## Testing

```python
from a2kit.packages.testing import make_test_app

def test_get_task():
    app = make_test_app([TasksRouter()], overrides={get_conn: fake_conn})
    # ... invoke a tool through the test app
```

`make_test_app` rebuilds tools with `Depends(fake)` patched in via `uncalled_for` primitives. There is no `app.dependency_overrides` map.

## Migration from v0.x

See [CHANGELOG.md](CHANGELOG.md) for the v1.0 break notes:

- DI form: `Annotated[T, Depends(g)]` → `T = Depends(g)` (parameter default)
- Import paths: `a2kit.di` → `uncalled_for`, `a2kit.contrib.connections` → `a2kit.packages.connections`, `a2kit.scaffold` → `a2kit`, `a2kit.testing` → `a2kit.packages.testing`
- Connection contract: lazy → eager substitution
- Override pattern: `dependency_overrides` map → `make_test_app(...)`
- CLI entry: `app.run()` → `a2kit.run(app)`
- Filter syntax: legacy `--select` atoms → real CEL (`&&` / `||` / `!`)

See [ANTIPATTERNS.md](ANTIPATTERNS.md) for a2kit-specific patterns to avoid.

## Status

v1.0 is a clean break. No v0.x compat shims, no deprecated aliases.

**Type-correctness gate.** `make lint` runs `uv run ty check src/` (Astral
[`ty`](https://github.com/astral-sh/ty)) as a hard gate. The repo carries
zero `# ty: ignore` comments — verified by
`tests/test_type_correctness_gate.py`. Any new diagnostic blocks the
lint target until fixed at the source, not silenced.
