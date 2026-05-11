# a2kit

**Fat tool decorator on top of FastMCP — protocol-agnostic core, plain-Python composition.**

a2kit ships an `App`, verb decorators (`@a2kit.read` / `@a2kit.write` /
`@a2kit.list_`), and a `ToolContext` alias for `fastmcp.Context` — that's it
for the core.
Connections, formatter, select grammar, lint, testing helpers, MCP server,
and CLI live under `a2kit.packages.*` and are imported only when you
actually use them. FastMCP is a hard dependency, but it's confined to
`a2kit.packages.mcp` — `import a2kit` stays under 100 ms.

A single console script handles every mode — tool subcommands, connection
management, schema dump, and `serve`:

```python
# tracker/server.py — canonical imperative composition
import a2kit
from a2kit.packages.connections import connections, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

app = a2kit.App("tracker")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
app.add_router(connections(TrackerConn))   # installs TrackerConn provider via Router
app.add_cli(connections_cli(TrackerConn))  # adds the connections CLI subcommands
app.provide(TrackerStore)                  # class-as-factory; container reads __init__


def main() -> None:
    a2kit.run(app)
```

> **Style note.** The fluent chain (`a2kit.App(...).add_router(...).provide(...)`)
> still works as a shorthand for compact composition in tests and small scripts.
> Prefer the imperative form in real apps — each line names one subsystem,
> grep finds every install, no hidden side effects.

```toml
[project.scripts]
tracker = "tracker.server:main"
```

```bash
tracker --help
tracker tasks list-tasks --project-id=abc      # in-process; no MCP roundtrip
tracker connections login TrackerConn --key=default --field=db_path=./data.jsonl
tracker schema list-tasks                       # JSON; --jsonl for one-per-line
tracker serve --transport=stdio                 # only this loads fastmcp
```

## Install

```bash
uv pip install a2kit
```

## API surface

### Core (`a2kit`)

| Symbol | Purpose |
|---|---|
| `a2kit.App(name)` | Composition root. Three named verbs: `add_router(r)`, `add_cli(group)`, `add_mcp_middleware(m)`. Plus `provide(T, factory=None)` for typed request-scoped DI, and `set_ldd(...)` for the LDD kill-switch. `add_router(r)` is the canonical install verb — a Router carries tools and may also declare `providers = (...)`, `on_startup`/`on_shutdown` methods, and a custom `install(self, app)` hook for plugins. |
| `a2kit.Router` | Subclass; decorate methods with `@a2kit.read/write/list_`. Slug auto-derives (`TasksRouter` → `"tasks"`); explicit `name = "..."` overrides. Optional class attributes: `enrichers = [...]` (exception → user message), `providers = (...)` (typed DI providers installed by `add_router`). Optional methods: `on_startup`/`on_shutdown` (lifecycle), `install(self, app)` (custom plumbing). |
| `a2kit.RouterRegistry` | Internal; collects `Router` instances. |
| `a2kit.Surface` | `Flag` — `CLI`, `MCP`, `ALL`. Pass to any verb decorator (`@a2kit.read(surfaces=Surface.CLI)`) to constrain which transports the tool mounts on. Default `Surface.ALL`. Credential-management tools should declare `Surface.CLI` — lint rule `A2K-SURFACE-EXPLICIT` flags forgotten declarations. |
| `@a2kit.read / write / tool` | Verb decorators. Kwargs: `name?, tags?, annotations?, surfaces?`. |
| `@a2kit.list_` | Specialized list verb. `@a2kit.list_(*default_fields, page_size=None, selectable_fields=None, name=None, tags=None)`. Selectable derived from `list[T]` return annotation when omitted. |
| `a2kit.A2KitMeta` | Frozen typed contract stamped onto each tool fn (`fn._a2kit`). Feature decorators write namespaced keys into `meta.extra`. |
| `a2kit.ToolContext` | Lazy alias for `fastmcp.Context` — tools annotate `ctx: a2kit.ToolContext` and receive the live FastMCP Context on the MCP transport, or a Context-shaped CLI stub on the CLI transport. Bare `import a2kit` doesn't pull fastmcp; the alias resolves on first access. |
| `a2kit.Cap` | Built-in capability `StrEnum`. `a2kit.capabilities.register(...)` for custom tags. |
| `a2kit.run(app, argv=None)` | Single-entry CLI dispatch. Builds Click group, invokes. |

### Plugin packages (`a2kit.packages.*`)

| Package | Purpose |
|---|---|
| `a2kit.packages.mcp` | FastMCP adapter. `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. The ONE place fastmcp imports. |
| `a2kit.packages.cli` | Click adapter. `build_full_cli(app)` returns the progressive-disclosure CLI. |
| `a2kit.packages.connections` | `ConnectionConfig`, `ConnectionStore`, `connections_cli(*types)` — plain Python; the CLI factory mounts via `app.add_cli(...)`. Carries the `Container` (request-scoped DI) consumed via `App.provide(...)`. |
| `a2kit.packages.formatter` | Type-driven output routing — TSV / JSON / hybrid `page-tsv`. `format_response(raw, format_hint=...)`. Auto picks based on the tool's return-type annotation. |
| `a2kit.packages.select` | `compile`, `evaluate`, `validate_atoms` over real CEL syntax. |
| `a2kit.packages.mcp.reports` | `reports(ReportT)` stacked decorator. Computes the pydantic JSON schema; both keys travel on `meta.extra`. |
| `a2kit.packages.testing` | Thin pytest fixtures + `compute_schema` helper. |
| `a2kit.packages.lint` | Static + runtime A2K rules. `a2kit lint static <path>` / `a2kit lint runtime --import pkg:app`. |

### Dependency injection — typed, request-scoped, sync

Tool methods declare their dependencies as typed kwargs. The container in
`packages/di` resolves them per call by reading `__init__` annotations.
The container is **synchronous** — factories must be `def`, not `async def`.
For async-opened resources (sqlite, browser pools, HTTP clients), use the
[Resource pattern](#resource-pattern-lazy-init) described below.

Connection-scoped state flows from the wire `connection: str` through the
connections package's **dispatch hook** (not through the container). The
hook awaits the typed `ConnectionConfig` from the configured store, then
hands off to the synchronous container for the rest of DI. The container
itself contains no reference to `"connection"`.

```python
import a2kit
from a2kit.packages.connections import connections_cli

from .connection import TrackerConn          # subclass of ConnectionConfig
from .store import TrackerStore              # def __init__(self, conn: TrackerConn)


class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task:
        return store.get(task_id)


app = a2kit.App("tracker")
app.add_router(TasksRouter())
app.add_router(connections(TrackerConn))   # installs TrackerConn provider
app.add_cli(connections_cli(TrackerConn))  # adds the connections CLI subcommands
app.provide(TrackerStore)                  # class-as-factory (introspects __init__)
```

What the framework does:

- `connections(TrackerConn)` returns a Router whose `install()` registers the **dispatch hook** (which awaits `store.load(connection)` and substitutes the typed `TrackerConn` into the per-call DI cache) and a stub provider for `TrackerConn` (so `container.has()` is True for schema-gen). `connections_cli(TrackerConn)` adds the matching Click subcommands.
- `provide(TrackerStore)` registers `TrackerStore` as its own factory; the container reads `TrackerStore.__init__(conn: TrackerConn)` and chains.
- At dispatch: the connections dispatch hook (async) awaits the connection load; the typed `TrackerConn` is seeded into the container's per-call cache; the rest of the chain resolves synchronously. The wire schema strips `store`; agents see only `connection` + `task_id`.
- For one-off non-trivial wiring, pass an explicit sync factory: `app.provide(SearchIndex, lambda store: SearchIndex.warm(store))`. Last-write-wins lets tests override providers.

No `Depends(...)`, no class-as-key markers, no plugin protocol. The
`provide(...)` calls *are* the DI graph; you can grep for them.

### Resource pattern (lazy-init)

DI factories are sync. For resources that need an event loop to open
(`aiosqlite.connect`, browser pools, async HTTP clients), encapsulate the
open inside a resource class with its own internal lock. AppState holds
resource handles as non-Optional fields; they self-initialize on first call:

```python
import asyncio
import aiosqlite


class SqliteResource:
    """Opens lazily on first await; close from @on_shutdown."""

    def __init__(self, settings: SqliteSettings) -> None:
        self.settings = settings
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is not None:
            return self._conn
        async with self._lock:
            if self._conn is None:
                self._conn = await aiosqlite.connect(self.settings.path)
            return self._conn

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        return await (await self._ensure()).execute(sql, params)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


@dataclass(slots=True)
class AppState:
    settings: AppSettings
    sqlite: SqliteResource          # never None
    browser: BrowserPool            # never None
    # locks live INSIDE the resources, never on AppState


def build_state(settings: AppSettings) -> AppState:    # sync!
    return AppState(
        settings=settings,
        sqlite=SqliteResource(settings.sqlite),
        browser=BrowserPool(settings.browser),
    )


app = a2kit.App("my-app")
app.singleton(AppState, build_state)

@app.on_shutdown
async def _close(state: AppState) -> None:
    await state.sqlite.close()
    await state.browser.close()


# Optional fail-fast warm-up at startup:
@app.on_startup
async def _warm(state: AppState) -> None:
    await state.sqlite._ensure()    # surface config errors at startup, not first call
```

What you get:
- AppState fields never Optional. Every call site sees a real resource.
- Locks live inside resources, not leaking into state.
- DI stays sync. Composition is plain `__init__`.
- Each resource owns its open + close idempotently.

### Lifecycle hooks are DI-aware

`@app.on_startup` and `@app.on_shutdown` resolve their typed kwargs through
the container, the same way `@app.health_check` does. Handlers take
whatever they need:

```python
@app.on_startup
async def _open(state: AppState) -> None:       # DI-resolved
    await state.sqlite._ensure()

@app.on_shutdown
async def _close(state: AppState, settings: AppSettings) -> None:
    await state.sqlite.close()
```

No more `_app.container().resolve(AppState)` dance. Hooks read like any
other DI-aware function.

### MCP tool annotations

Verb decorators accept the MCP `ToolAnnotations` hints that clients use to
decide things like "should I auto-invoke without confirmation?" or "how
much trust to extend to repeated calls?".

```python
@a2kit.read(idempotent=True, open_world=True, title="Fetch Web Page")
async def fetch(*, url: str) -> FetchResponse:
    ...

@a2kit.write(destructive=False, idempotent=True, title="Mark Complete")
async def mark_complete(*, task_id: str) -> Task:
    ...
```

Defaults are conservative: `idempotent=False`, `open_world=False`,
`destructive=False` on `@read`, `True` on `@write`. Apps that touch the
network must opt into `open_world=True`. `@a2kit.read(destructive=...)`
raises `TypeError` — read tools are non-destructive by spec. The full
escape hatch is `annotations=ToolAnnotations(...)` if you need to set
fields a2kit doesn't model.

### Per-parameter descriptions

`a2kit.Param("Absolute URL.")` (positional shorthand) or
`a2kit.Param(description="...")` (keyword form) attaches schema metadata to
direct kwargs (non-model parameters):

```python
from typing import Annotated

@a2kit.read()
async def fetch(
    *,
    # Positional shorthand — cosmetically shorter for one-line descriptions.
    url: Annotated[str, a2kit.Param("Absolute http(s) URL.")],
    # Keyword form — clearer when the description is multi-line or you want
    # to mix in other Field kwargs (examples=, ge=, le=, etc.).
    include_links: Annotated[
        bool,
        a2kit.Param(
            description=(
                "Include the extracted `links` array in the response. "
                "Default False — links are a large share of payload bytes "
                "on aggregator pages."
            ),
        ),
    ] = False,
) -> FetchResponse:
    """First line is the short description.

    The full body is the long help — markdown stripped on CLI, intact on MCP.
    """
```

Long descriptions are intentional — MCP agents read them via `list_tools` to
decide whether/how to call your tool. Use the kwarg form for prose;
use the positional shorthand for short one-liners.

Passing both the positional and the `description=` kwarg raises `TypeError`
(Python's natural "got multiple values for argument 'description'").

The description flows to both the MCP input schema (via pydantic) and
click `--option HELP`. For kwargs that are Pydantic body models,
`Field(description=...)` already works — `Param` is the sibling for
direct kwargs.

### Health probe

```python
app = a2kit.App("my-app", health_tool=True)

@app.health_check
async def _sqlite() -> a2kit.HealthResult:
    return a2kit.HealthResult.ok() if state.sqlite else a2kit.HealthResult.fail("not opened")
```

Registers a built-in `_meta.health` tool (hidden from agent-facing
`list_tools` but invokable by name). CLI exposes `<app> health` whose exit
code reflects aggregated status. The `_meta.*` namespace is reserved —
user tools can't claim it.

### Logging + progress + events + reports (`ToolContext`)

`a2kit.ToolContext` is an alias for `fastmcp.Context`. All Context logging
methods are async; events and reports moved off the Context class and live
as free functions in `a2kit.ldd`.

| Channel | API | When to use |
|---|---|---|
| Process telemetry | `await ctx.info / warning / error / debug(msg, **kw)` | Free-form ambient logs |
| Numeric progress | `await ctx.report_progress(i, n)` | "30 of 100" — for progress bars |
| **Narrative events (kwargs)** | `await event(ctx, "name.string", **payload)` (from `a2kit.ldd`) | Typed milestones agents pattern-match (e.g. `"api.fetched"`) |
| **Narrative events (typed)** | `await event(ctx, MyEvent(...))` — instance second positional | Pass a dataclass / pydantic model directly; name defaults to class name, fields serialize via `dataclasses.asdict` / `model_dump`. Enum fields coerced via `.value`. |
| **Typed reports** | `await report(ctx, payload)` (requires stacked `@reports(ReportT)`) | Mid-flight result chunks with a declared schema |
| **Typed event registry** | `app.ldd.events.register(MyEvent, progress=fn)` then `await app.ldd.events.emit_typed(ctx, evt)` | One-call emit: dump → event → progress (use this when you also need progress reporting) |

```python
from pydantic import BaseModel
from a2kit.ldd import event, report
from a2kit.packages.mcp.reports import reports


class BatchReport(BaseModel):
    batch: int
    accepted: int


@a2kit.read()
@reports(BatchReport)
async def bulk_import(*, ctx: a2kit.ToolContext, file: str) -> dict:
    await event(ctx, "import.started", file=file)
    items = await load(file)
    for i, item in enumerate(items):
        await ctx.report_progress(i, len(items))
        await report(ctx, BatchReport(batch=i, accepted=1))
    # Typed form: pass an instance directly. Name = class name; payload serializes
    # via model_dump / dataclasses.asdict.
    await event(ctx, ImportComplete(count=len(items)))
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

**Lint rule.** `A2K-LDD-REPORT-TYPE` fires when `report(ctx, ...)` is
called without a stacked `@reports(ReportT)` decorator, or when the
declared type is defined inside a function (Pydantic forward-ref constraint).

The `ctx` parameter is stripped from the input schema and from CLI
option generation.

## CLI

`a2kit.run(app)` exposes:

- `<app> --help` — top-level: one entry per Router (with progressive-disclosure hint), plus `schema`, `serve`, plus any subcommand attached via `app.add_cli(...)`.
- `<app> <router> --help` — list tools in that router.
- `<app> <router> <tool> [--name VALUE ...] [--format=auto|json|tsv|page-tsv] [--schema]` — invoke the tool in-process. Output flows through the formatter; `auto` picks based on the tool's return-type annotation (`list[ScalarOnlyModel]` → TSV, `Page[T]` → hybrid `page-tsv`, else JSON).
- `<app> connections {login,logout,list,show,delete}` — present iff the app wired `connections_cli(...)` via `add_cli`.
- `<app> schema [TOOL] [--format=auto|json|tsv] [--jsonl]` — schema discovery.
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
- `A2K-LDD-REPORT-TYPE` — `report(ctx, ...)` without a stacked `@reports(ReportT)`, or report type defined inside a function.
- `A2K-CORE-CLEAN` — feature identifiers (`connection`, `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug`) in `src/a2kit/*.py` outside `packages/`. Same boundary keeps the DI container (`Container`, `partition_kwargs`, `apply_kwargs`) confined to `packages/connections`.
- `A2K-EXTRA-NAMESPACE` — `meta.extra` keys must start with `a2kit.` or a `<package>.` prefix.

## Testing

### In-process test client (recommended)

`a2kit.testing.client(app)` runs the **full dispatcher** in-process — same
DI resolution, decorator processing, return-value rendering, and `ctx`
wiring as production. Lifecycle hooks fire. Events / progress / logs /
reports are captured for assertions.

```python
import asyncio
import a2kit
from a2kit.testing import client

async def test_fetch():
    async with client(app) as c:
        result = await c.invoke("web.fetch", url="https://example.com")
        assert result.status == "ok"
        assert any(e["name"] == "TierEnded" for e in c.events)
        assert c.progress[-1] == (1.0, 1.0)
        # Cross-format assertion without spinning a real MCP server:
        assert c.render_as("json", result)["status"] == "ok"
```

`client.invoke` returns the raw tool value (no formatter). `client.render_as(fmt, val)`
runs the value through `a2kit.packages.formatter` for wire-format checks.
`client.tools()` returns descriptors matching what `list_tools` would
advertise. `connection=` flows through the same DI chain as the CLI/MCP
transports.

### Null context for internal phase tests

For unit tests of internal phase functions that bypass the dispatcher, use
`a2kit.testing.null_context()` — a no-op `ToolContext`-shaped shim:

```python
from a2kit.testing import null_context

async def test_phase() -> None:
    ctx = null_context()                              # silent ToolContext shim
    await fetch_tier(ctx, url="https://example.com")  # no-op event emit, no I/O
```

Production code can take `ctx: a2kit.ToolContext` (non-Optional) and the test
constructs the shim instead of passing `None`. Every wire method (logging,
progress, event emit, report, sample, list_*) is a silent no-op.

### Direct construction (lightweight unit tests)

For tests that don't need the full dispatcher, construct routers with fake
factories and register them with a fresh `App`:

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
See [OPERATIONAL_CONTRACTS.md](OPERATIONAL_CONTRACTS.md) for documented
behaviors on cancellation, timeouts, multi-App, errors, and streaming.

## Status

v0.20 is a clean break from v0.19. No compat shims, no deprecated aliases.

**Type-correctness gate.** `make lint` runs `uv run ty check src/` (Astral
[`ty`](https://github.com/astral-sh/ty)) as a hard gate. The repo carries
zero `# ty: ignore` comments — verified by
`tests/test_type_correctness_gate.py`. Any new diagnostic blocks the
lint target until fixed at the source, not silenced.
