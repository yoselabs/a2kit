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
from a2kit.packages.connections import connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

app = (
    a2kit.App("tracker")
    .add_router(ProjectsRouter())
    .add_router(TasksRouter())
    .provide(TrackerStore)                   # class-as-factory; container reads __init__
    .add_cli(connections_cli(TrackerConn))   # auto-installs TrackerConn provider
)


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
| `a2kit.App(name)` | Composition root. Three named verbs: `add_router(r)`, `add_cli(group)`, `add_mcp_middleware(m)`. Plus `provide(T, factory=None)` for typed request-scoped DI, and `set_ldd(...)` for the LDD kill-switch. |
| `a2kit.Router` | Subclass; decorate methods with `@a2kit.read/write/list_`. Slug auto-derives (`TasksRouter` → `"tasks"`); explicit `name = "..."` overrides. Class attribute `enrichers = [...]` and optional `def enrich(self, exc)` map exceptions to user-facing messages. |
| `a2kit.RouterRegistry` | Internal; collects `Router` instances. |
| `@a2kit.read / write / tool` | Verb decorators. Kwargs: `name?, tags?, annotations?`. |
| `@a2kit.list_` | Specialized list verb. `@a2kit.list_(*default_fields, page_size=None, selectable_fields=None, name=None, tags=None)`. Selectable derived from `list[T]` return annotation when omitted. |
| `a2kit.A2KitMeta` | Frozen typed contract stamped onto each tool fn (`fn._a2kit`). Feature decorators write namespaced keys into `meta.extra`. |
| `a2kit.ToolContext` | Protocol for protocol-neutral logging + progress. Both adapters supply an implementation. |
| `a2kit.Cap` | Built-in capability `StrEnum`. `a2kit.capabilities.register(...)` for custom tags. |
| `a2kit.run(app, argv=None)` | Single-entry CLI dispatch. Builds Click group, invokes. |

### Plugin packages (`a2kit.packages.*`)

| Package | Purpose |
|---|---|
| `a2kit.packages.mcp` | FastMCP adapter. `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. The ONE place fastmcp imports. |
| `a2kit.packages.cli` | Click adapter. `build_full_cli(app)` returns the progressive-disclosure CLI. |
| `a2kit.packages.connections` | `ConnectionConfig`, `ConnectionStore`, `connections_cli(*types)` — plain Python; the CLI factory mounts via `app.add_cli(...)`. Carries the `Container` (request-scoped DI) consumed via `App.provide(...)`. |
| `a2kit.packages.formatter` | TOON / JSON output normalization via `toon-format`. `format_response(raw, format_hint=...)`. |
| `a2kit.packages.select` | `compile`, `evaluate`, `validate_atoms` over real CEL syntax. |
| `a2kit.packages.mcp.reports` | `reports(ReportT)` stacked decorator. Computes the pydantic JSON schema; both keys travel on `meta.extra`. |
| `a2kit.packages.testing` | Thin pytest fixtures, syrupy `TOONSnapshotExtension`. |
| `a2kit.packages.lint` | Static + runtime A2K rules. `a2kit lint static <path>` / `a2kit lint runtime --import pkg:app`. |

### Dependency injection — typed, request-scoped

Tool methods declare their dependencies as typed kwargs. The container in
`packages/connections` resolves them per call by reading `__init__`
annotations. Connection-scoped state flows from the wire `connection: str`
through the auto-installed `ConnectionConfig` provider.

```python
import a2kit
from a2kit.packages.connections import connections_cli

from .connection import TrackerConn          # subclass of ConnectionConfig
from .store import TrackerStore              # def __init__(self, conn: TrackerConn)


class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task:
        return store.get(task_id)


app = (
    a2kit.App("tracker")
    .add_router(TasksRouter())
    .provide(TrackerStore)                   # class-as-factory (introspects __init__)
    .add_cli(connections_cli(TrackerConn))   # auto-installs TrackerConn provider
)
```

What the framework does:

- `connections_cli(TrackerConn)` carries a marker that `add_cli` reads to install a typed provider for `TrackerConn` (`connection: str → TrackerConn`).
- `provide(TrackerStore)` registers `TrackerStore` as its own factory; the container reads `TrackerStore.__init__(conn: TrackerConn)` and chains.
- At dispatch: `store: TrackerStore` is resolved per call from the wire `connection`. Two kwargs of the same type share one instance within a call (per-call cache). The wire schema strips `store`; agents only see `connection` + `task_id`.
- For one-off non-trivial wiring, pass an explicit factory: `app.provide(SearchIndex, lambda store: SearchIndex.warm(store))`. Last-write-wins lets tests override providers.

No `Depends(...)`, no class-as-key markers, no plugin protocol. The
`provide(...)` calls *are* the DI graph; you can grep for them.

### Logging + progress + events + reports (`ToolContext`)

`ToolContext` exposes **four channels** for mid-flight communication.
Each emission carries an elapsed `+s.mmm` timestamp and reaches the
caller immediately (no buffering).

| Channel | API | When to use |
|---|---|---|
| Process telemetry | `ctx.info / warning / error / debug(msg, **kw)` | Free-form ambient logs |
| Numeric progress | `await ctx.report_progress(i, n)` | "30 of 100" — for progress bars |
| **Narrative events** | `await ctx.event(name, **payload)` | Typed milestones agents pattern-match (e.g. `"api.fetched"`) |
| **Typed reports** | `await ctx.report(payload)` (requires stacked `@reports(ReportT)`) | Mid-flight result chunks with a declared schema |

```python
from pydantic import BaseModel


class BatchReport(BaseModel):
    batch: int
    accepted: int


from a2kit.packages.mcp.reports import reports


@a2kit.read()
@reports(BatchReport)
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
emissions still type-validate `@reports(...)` payloads — keeps tests
deterministic.

**Lint rule.** `A2K-LDD-REPORT-TYPE` fires when `ctx.report(...)` is
called without a stacked `@reports(ReportT)` decorator, or when the
declared type is defined inside a function (Pydantic forward-ref constraint).

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

Active rules:

- `A2K-CONN-LIST-PLACEHOLDER` — `${VAR}` inside list/dict fields on `ConnectionConfig`.
- `A2K-IMPORT-DISCIPLINE` — `fastmcp` imports outside `packages/mcp/` and the lazy-load lines in `packages/cli/builder.py`.
- `A2K-LDD-REPORT-TYPE` — `ctx.report(...)` without a stacked `@reports(ReportT)`, or report type defined inside a function.
- `A2K-CORE-CLEAN` — feature identifiers (`connection`, `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug`) in `src/a2kit/*.py` outside `packages/`. Same boundary keeps the DI container (`Container`, `partition_kwargs`, `apply_kwargs`) confined to `packages/connections`.
- `A2K-EXTRA-NAMESPACE` — `meta.extra` keys must start with `a2kit.` or a `<package>.` prefix.

## Testing

Tests construct routers with fake factories and register them with a fresh
`App` — same shape as production code:

```python
import a2kit


def test_get_task() -> None:
    def fake_store_factory(conn: TrackerConn) -> TrackerStore:
        return FakeStore()

    app = (
        a2kit.App("test")
        .add_router(TasksRouter())
        .provide(TrackerConn, lambda connection: TrackerConn(key=(connection,), db_path="/tmp/x"))
        .provide(TrackerStore, fake_store_factory)
    )
    fn = app.tools()[0]
    # ... invoke through the test app
```

Provider override is just `app.provide(T, fake)` — last-write-wins. No
`dependency_overrides` map, no `make_test_app` helper. The `app` pytest
fixture in `a2kit.packages.testing` returns a fresh `a2kit.App("test")`.

## Migration from v0.x

See [CHANGELOG.md](CHANGELOG.md) for the v0.20 break notes. From the
v0.19 / `v1-thin-core` intermediate shapes:

- `Depends(<class>)` / `Depends(<callable>)` → typed kwargs on tool methods + `app.provide(T, factory=None)`
- `app.use(...)` → `app.add_router(...)`, `app.add_cli(...)`, `app.add_mcp_middleware(...)`
- `app.connect(C)` → (delete; conn config is just a class)
- `app.use_factory(...)` → `app.provide(T, factory)` (or `app.provide(T)` for class-as-factory)
- `class TrackerStore(a2kit.Store[TrackerConn]):` → `class TrackerStore:` (plain class)
- `class R(a2kit.Router, enricher=fn):` (pre-v0.21) / per-tool `@enriches(fn)` (v0.21) → class attribute `enrichers = [fn, ...]` and/or `def enrich(self, exc) -> str | None`
- `@a2kit.read(enricher=…, list_view=…, report=…)` (v0.20) / stacked `@enriches/@lists/@reports` (v0.21) → enrichers are class-side; list-view absorbed into `@a2kit.list_(*default_fields, page_size=, selectable_fields=)`; only `@reports` remains stacked
- `def __init__(self, get_store: GetStore)` factory closure → declare `store: TrackerStore` directly on tool methods; `app.provide(TrackerStore)` registers the class
- `name = "tasks"` ceremonial line → derived from class name automatically (`class TasksRouter` → `"tasks"`); explicit `name = "..."` still wins
- `from a2kit.exceptions import WriteNotAllowed` → `from a2kit.packages.connections.exceptions import WriteNotAllowed`
- `make_test_app(routers, overrides=...)` → construct App + routers directly; override providers via `app.provide(T, fake)` (last-write-wins)
- `Connections()` plugin → `ConnectionStore(...)` + `connections_cli(...)` direct usage; `add_cli(connections_cli(ConfigT))` auto-installs the `ConfigT` provider

See [ANTIPATTERNS.md](ANTIPATTERNS.md) for a2kit-specific patterns to avoid.

## Status

v0.20 is a clean break from v0.19. No compat shims, no deprecated aliases.

**Type-correctness gate.** `make lint` runs `uv run ty check src/` (Astral
[`ty`](https://github.com/astral-sh/ty)) as a hard gate. The repo carries
zero `# ty: ignore` comments — verified by
`tests/test_type_correctness_gate.py`. Any new diagnostic blocks the
lint target until fixed at the source, not silenced.
