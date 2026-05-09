# a2kit

**Fat tool decorator on top of FastMCP — protocol-agnostic core, plain-Python composition.**

a2kit ships an `App`, verb decorators (`@a2kit.read` / `@a2kit.write` /
`@a2kit.list_`), and a `ToolContext` Protocol — that's it for the core.
Connections, formatter, select grammar, lint, testing helpers, MCP server,
and CLI live under `a2kit.packages.*` and are imported only when you
actually use them. FastMCP is a hard dependency, but it's confined to
`a2kit.packages.mcp` — `import a2kit` stays under 100 ms.

A single console script handles every mode — tool subcommands, connection
management, schema dump, and `serve`:

```python
# tracker/server.py
import a2kit
from a2kit.packages.connections import ConnectionStore, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

_conn_store = ConnectionStore(TrackerConn)


async def get_store(connection: str) -> TrackerStore:
    conn = await _conn_store.load((connection,))
    return TrackerStore(conn)


app = a2kit.App("tracker")
app.add_router(ProjectsRouter(get_store))
app.add_router(TasksRouter(get_store))
app.add_cli(connections_cli(TrackerConn))


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
tracker connections login TrackerConn --key=default --field=db_path=./data.jsonl
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
| `a2kit.App(name)` | Composition root. Three named verbs: `add_router(r)`, `add_cli(group)`, `add_mcp_middleware(m)`. Plus `set_ldd(...)` for the LDD kill-switch. |
| `a2kit.Router` | Subclass; decorate methods with `@a2kit.read/write/list_`. Pass factories via `__init__`; the framework does no DI introspection. |
| `a2kit.RouterRegistry` | Internal; collects `Router` instances. |
| `@a2kit.tool / read / write / list_` | Verb decorators. Map to `mcp.types.ToolAnnotations` + tags. Optional `enricher=fn` per-tool. |
| `a2kit.A2KitMeta` | Frozen typed contract stamped onto each tool fn (`fn._a2kit`). |
| `a2kit.ToolContext` | Protocol for protocol-neutral logging + progress. Both adapters supply an implementation. |
| `a2kit.Cap` | Built-in capability `StrEnum`. `a2kit.capabilities.register(...)` for custom tags. |
| `a2kit.run(app, argv=None)` | Single-entry CLI dispatch. Builds Click group, invokes. |

### Plugin packages (`a2kit.packages.*`)

| Package | Purpose |
|---|---|
| `a2kit.packages.mcp` | FastMCP adapter. `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. The ONE place fastmcp imports. |
| `a2kit.packages.cli` | Click adapter. `build_full_cli(app)` returns the progressive-disclosure CLI. |
| `a2kit.packages.connections` | `ConnectionConfig`, `ConnectionStore`, `connections_cli(*types)` — plain Python; the CLI factory mounts via `app.add_cli(...)`. |
| `a2kit.packages.formatter` | TOON / JSON output normalization via `toon-format`. `format_response(raw, format_hint=...)`. |
| `a2kit.packages.select` | `compile`, `evaluate`, `validate_atoms` over real CEL syntax. |
| `a2kit.packages.enrichers` | Concrete enricher implementations (e.g. `connection_enricher`). The wrap mechanism itself lives in core. |
| `a2kit.packages.testing` | Thin pytest fixtures, syrupy `TOONSnapshotExtension`. |
| `a2kit.packages.lint` | Static + runtime A2K rules. `a2kit lint static <path>` / `a2kit lint runtime --import pkg:app`. |

### Dependency injection — constructor injection

Routers receive their dependencies through `__init__`. Tools access them via
`self`. The framework introspects nothing.

```python
import a2kit


class TasksRouter(a2kit.Router):
    def __init__(self, get_store) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.read()
    async def get_task(self, *, connection: str, task_id: str) -> Task:
        store = await self.get_store(connection)
        return store.get(task_id)


app = a2kit.App("tracker")
app.add_router(TasksRouter(get_store))
```

That's it. No `Depends(...)`, no class-as-key, no Generic markers, no
plugin protocol. A reader unfamiliar with a2kit can predict every line's
behavior without reading the framework source.

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

- `<app> --help` — top-level: one entry per Router (with progressive-disclosure hint), plus `schema`, `serve`, plus any subcommand attached via `app.add_cli(...)`.
- `<app> <router> --help` — list tools in that router.
- `<app> <router> <tool> [--name VALUE ...] [--format=auto|toon|json] [--schema]` — invoke the tool in-process. Output flows through the formatter.
- `<app> connections {login,logout,list,show,delete}` — present iff the app wired `connections_cli(...)` via `add_cli`.
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

- `A2K-CONN-LIST-PLACEHOLDER` — `${VAR}` inside list/dict fields on `ConnectionConfig`.
- `A2K-IMPORT-DISCIPLINE` — `fastmcp` imports outside `packages/mcp/` and the lazy-load lines in `packages/cli/builder.py`.
- `A2K-LDD-REPORT-TYPE` — `ctx.report(...)` without `report=` on the decorator, or report type defined inside a function.

## Testing

Tests construct routers with fake factories and register them with a fresh
`App` — same shape as production code:

```python
import a2kit


def test_get_task() -> None:
    async def fake_get_store(connection: str):
        return FakeStore()

    app = a2kit.App("test")
    app.add_router(TasksRouter(fake_get_store))
    fn = app.tools()[0]
    # ... invoke through the test app
```

No `app.dependency_overrides` map. No `make_test_app` helper. The `app`
pytest fixture in `a2kit.packages.testing` returns a fresh `a2kit.App("test")`.

## Migration from v0.x

See [CHANGELOG.md](CHANGELOG.md) for the v1.0 break notes. From the
prior `v1-thin-core` shape:

- `Depends(<class>)` and `Depends(<callable>)` → constructor injection
- `app.use(...)` → `app.add_router(...)`, `app.add_cli(...)`, `app.add_mcp_middleware(...)`
- `app.connect(C)` → (delete; conn config is just a class)
- `app.use_factory(...)` → pass factory to router constructor
- `class TrackerStore(a2kit.Store[TrackerConn]):` → `class TrackerStore:` (plain class)
- `class R(a2kit.Router, enricher=fn):` → per-tool `@a2kit.read(enricher=fn)`
- `make_test_app(routers, overrides=...)` → construct App + routers directly
- `Connections()` plugin → `ConnectionStore(...)` + `connections_cli(...)` direct usage

See [ANTIPATTERNS.md](ANTIPATTERNS.md) for a2kit-specific patterns to avoid.

## Status

v1.0 is a clean break. No v0.x compat shims, no deprecated aliases.

**Type-correctness gate.** `make lint` runs `uv run ty check src/` (Astral
[`ty`](https://github.com/astral-sh/ty)) as a hard gate. The repo carries
zero `# ty: ignore` comments — verified by
`tests/test_type_correctness_gate.py`. Any new diagnostic blocks the
lint target until fixed at the source, not silenced.
