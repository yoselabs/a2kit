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
from a2kit.packages.connections import connections_cli, install_connections

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

app = a2kit.App("tracker")
app.add_router(ProjectsRouter())
app.add_router(TasksRouter())
install_connections(app, TrackerConn)      # dispatch hook + typed wire scope
app.add_cli(connections_cli(TrackerConn))  # adds the connections CLI subcommands
app.provide(TrackerStore)                  # class-as-factory; container reads __init__


def main() -> None:
    a2kit.run(app)
```

> **One App, built by the finisher.** `a2kit.App` is the single public
> type — the mutable composition surface (`add_router`, `add_cli`,
> `add_mcp_middleware`, `provide`, `health_check`). Hand it to a finisher
> (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`) and the
> finisher builds it into a sealed internal runtime: snapshots the
> composition into a fresh container, validates the provider graph, owns
> the lifecycle. The fluent chain
> (`a2kit.App(...).add_router(...).provide(...)`) works as a shorthand
> for compact composition in tests and small scripts; prefer the
> imperative form in real apps — each line names one subsystem, grep
> finds every install. There is no public `build()`; `App` is a pure,
> reusable builder — a composition verb after a finisher has built a
> runtime affects only the next build. See ADR 0019.

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
| `a2kit.App(name, *, debug=False)` | The single public type — a compose-phase builder. Three named verbs: `add_router(r)`, `add_cli(group)`, `add_mcp_middleware(m)`. Plus `provide(T, factory=None, *, per_call=False)` for typed DI and `health_check` for readiness probes. Each verb returns the App for chaining. Introspection surface: `tools()`, `routers()`, `container()`, `set_ldd(...)` (LDD kill-switch). `add_router(r)` is the canonical install verb — a Router carries tools and may also declare `providers = (...)` and `__aenter__`/`__aexit__` for router-scoped lifecycle. Hand the App to a finisher (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`); the finisher builds it into a sealed internal runtime (snapshots the composition into a fresh container, validates the provider graph, owns the async-CM lifecycle). There is no public `build()`. `App` is a pure, reusable builder — composition verbs stay callable, and a verb called after a finisher has built a runtime affects only the next build. |
| `a2kit.Router` | Subclass; decorate methods with `@a2kit.read/write/list_`. Subclasses MUST declare `slug: ClassVar[str]` and `tools: ClassVar[tuple]`. Optional class attributes: `enrichers = (...)` (exception → user message), `providers = (...)` (typed DI providers installed by `add_router`), `visibility = "..."` (default tier for tools). Optional `lifespan` classmethod composes into the App's lifespan. |
| `a2kit.RouterRegistry` | Internal; collects `Router` instances. |
| `visibility=` kwarg | Verb decorators accept `visibility: Literal["hidden", "cli", "all"]`. Defaults to inherit from the Router's `visibility` class attribute (default `"all"`). Tier semantics: `"hidden"` — CLI-invokable but absent from `--help` and not on programmatic transports; `"cli"` — visible in `--help`, not on MCP / future REST; `"all"` — registered everywhere. Credential-management tools should declare `visibility="cli"` — lint rule `A2K-SURFACE-EXPLICIT` flags forgotten declarations. |
| `@a2kit.read` | Read-shaped verb. Kwargs: `open_world?, title?, visibility?, reports?, annotations?`. Reads are spec-idempotent and non-destructive — `idempotent=` and `destructive=` raise `TypeError`. |
| `@a2kit.write` | Write-shaped verb. Kwargs: `idempotent?, open_world?, destructive?, title?, visibility?, reports?, annotations?`. Defaults to `destructiveHint=True`. |
| `@a2kit.list_` | Specialized list verb (trailing underscore to avoid shadowing the built-in `list`). `@a2kit.list_(*default_fields, page_size=None, selectable_fields=None, open_world=False, title=None, visibility=None, reports=None)`. Requires a `list[T]` (or tuple/set/frozenset of T) return annotation at decoration time. `page_size` must be a positive integer or None. Selectable fields derive from `T` when omitted. |
| `a2kit.A2KitMeta` | Frozen typed contract stamped onto each tool fn (`fn._a2kit`). Feature decorators write namespaced keys into `meta.extra`. |
| `a2kit.ToolContext` | Lazy alias for `fastmcp.Context` — tools annotate `ctx: a2kit.ToolContext` and receive the live FastMCP Context on the MCP transport, or a Context-shaped CLI stub on the CLI transport. Bare `import a2kit` doesn't pull fastmcp; the alias resolves on first access. |
| `a2kit.run(app, argv=None)` | Single-entry CLI dispatch. Builds Click group, invokes. |

### Plugin packages (`a2kit.packages.*`)

| Package | Purpose |
|---|---|
| `a2kit.packages.mcp` | FastMCP adapter. `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`. Registers projection tools (`@a2kit.read/list/write`) and `@app.mcp.tool/.prompt/.resource` substrate-native registrations. The ONE place fastmcp imports. |
| `a2kit.packages.http` | FastAPI adapter. `build_http_app(runtime) -> fastapi.FastAPI`. Registers projection tools as `POST /api/<name>` and `@app.api.<method>(path)` author routes. Lazy: `import a2kit` does not pull fastapi. |
| `a2kit.packages.cli` | Click adapter. `build_full_cli(app)` returns the progressive-disclosure CLI. |
| `a2kit.packages.connections` | `ConnectionConfig`, `ConnectionStore`, `connections_cli(*types)` — plain Python; the CLI factory mounts via `app.add_cli(...)`. Carries the `Container` (request-scoped DI) consumed via `App.provide(...)`. |
| `a2kit.packages.formatter` | Consumer-aware rendering — `render(value, consumer)` for the `llm` / `code` / `machine` profiles; TSV / JSON / hybrid `page-tsv` wire forms picked by `build_encoding_plan` from the return type. `format_response` is the `format_hint`-shaped adapter. |
| `a2kit.packages.select` | `compile_selector(expr) -> Selector` — stdlib parser for the `serve --select EXPR` runtime filter. Categories: `verb`, `name` (fnmatch glob), `surface` (mcp/api). |
| `a2kit.packages.mcp.reports` | `reports(ReportT)` stacked decorator. Computes the pydantic JSON schema; both keys travel on `meta.extra`. |
| `a2kit.packages.testing` | Thin pytest fixtures + `compute_schema` helper. |
| `a2kit.packages.lint` | Static + runtime A2K rules. `a2kit lint static <path>` / `a2kit lint runtime --import pkg:app`. |

### Multi-surface authoring

One typed function reaches every transport. The framework offers three
decorator families on `App`, all driven by one signature-rewriting
mechanism so a2kit DI stays type-driven (no `Depends(...)` in author code).

```python
import a2kit

app = a2kit.App("memory").provide(Database, ...)

class R(a2kit.Router):
    slug = "memory"

    @a2kit.read                                       # both substrates
    async def fetch(self, *, id: str, db: Database) -> Memory: ...

    @a2kit.read(expose=("mcp",))                      # MCP only
    async def llm_fetch(self, *, id: str, db: Database) -> Memory: ...

    @a2kit.write(expose=("api",), authorize=admin_gate)  # API only + auth
    async def admin_upsert(self, *, item: Item, db: Database) -> Memory: ...

    tools = (fetch, llm_fetch, admin_upsert)

app.add_router(R())

# FastAPI-native — full @app.api.<method>(path, **fastapi_kwargs) surface
@app.api.get("/version", response_model=Version)
async def version(*, db: Database) -> Version:
    return Version(...)

# FastMCP-native — Prompts, Resources, full FastMCP kwargs
@app.mcp.prompt(name="summarize")
async def summarize(*, topic: str, db: Database) -> str:
    return ...
```

`serve --transport=http` auto-mounts each substrate sub-app based on
registrations: `/api` mounts if any projection tool exposes `api` or any
`@app.api.*` route exists; `/mcp` is the dual. Both substrates can serve
on one port. Operators narrow at deploy time with `--select`:

```bash
my-app serve --transport=http                       # both substrates
my-app serve --transport=http --select 'surface=mcp'  # MCP only
my-app serve --select 'verb=read,list'              # read-only mode
my-app serve --select 'name=fetch_*,!internal_*'    # pattern + exclude
```

DI test seam: re-provide on a fresh `App` (last-write-wins).
FastAPI's `dependency_overrides[T]` does **not** route to a2kit DI —
that mechanism keys on `Depends` callables; a2kit types are resolved
through `Container.call_scope`. See `tests/packages/http/test_dependency_override.py`.

See [ADR 0020](docs/adr/0020-multi-surface-authoring.md) for the full
decision record including the three-way substrate signature split,
POST-for-all routing rationale, and per-substrate wrapper emission.

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
from a2kit.packages.connections import connections_cli, install_connections

from .connection import TrackerConn          # subclass of ConnectionConfig
from .store import TrackerStore              # def __init__(self, conn: TrackerConn)


class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task:
        return store.get(task_id)


app = a2kit.App("tracker")
app.add_router(TasksRouter())
install_connections(app, TrackerConn)      # dispatch hook + typed wire scope
app.add_cli(connections_cli(TrackerConn))  # adds the connections CLI subcommands
app.provide(TrackerStore)                  # class-as-factory (introspects __init__)
```

What the framework does:

- `install_connections(app, TrackerConn)` registers the **dispatch hook** (which awaits `store.load(connection)` and substitutes the typed `TrackerConn` into the per-call DI cache) and a stub provider for `TrackerConn` (so `container.has_provider()` is True for schema-gen). `connections_cli(TrackerConn)` adds the matching Click subcommands.
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

    async def aclose(self) -> None:
        # Framework auto-detects ``aclose`` on the resolved singleton
        # and runs it when the runtime lifecycle unwinds.
        await self.browser.close()
        await self.sqlite.close()


def build_state(settings: AppSettings) -> AppState:    # sync!
    return AppState(
        settings=settings,
        sqlite=SqliteResource(settings.sqlite),
        browser=BrowserPool(settings.browser),
    )


app = a2kit.App("my-app").provide(AppState, build_state)
```

What you get:

- AppState fields never Optional. Every call site sees a real resource.
- Locks live inside resources, not leaking into state.
- DI stays sync. Composition is plain `__init__`.
- Each resource owns its open + close idempotently.

### Lifecycle

The finisher owns the runtime lifecycle. Handing an `App` to
`a2kit.run` / `build_mcp_server` / `a2kit.testing.client` builds a
sealed runtime and enters it: the DI container resolves resources
lazily on first use, auto-detecting the cleanup protocol on each
resolved instance (`__aexit__` paired with `__aenter__`). Routers opt
into lifecycle by implementing `__aenter__` / `__aexit__` and enter
lazily on first dispatch of any of their tools. Composition
(`add_router`, `provide`, ...) is pure — useful for tests that
introspect wiring without running anything.

```python
class DB:
    async def __aenter__(self) -> "DB":
        self.pool = await asyncpg.create_pool(DSN)
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.pool.close()


app = a2kit.App("my-app").provide(DB)


def main() -> None:
    # The finisher builds the runtime, enters its lifecycle, dispatches
    # tools, and unwinds on shutdown. DB enters lazily on the first
    # tool that resolves it.
    a2kit.run(app)
```

For router-scoped resources:

```python
class Github(a2kit.Router):
    slug = "gh"

    async def __aenter__(self) -> "Github":
        self.client = httpx.AsyncClient(base_url="https://api.github.com")
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.client.aclose()

    @a2kit.read()
    async def fetch(self, *, path: str) -> dict:
        return (await self.client.get(path)).json()

    tools = (fetch,)
```

For one-shot startup or shutdown work that has no associated resource
object, express it as a marker resource (a class with `__aenter__` /
`__aexit__`, registered via `app.provide(...)`) or do it in `main()`
before the finisher call — not via a framework hook.

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

Attach descriptions to direct kwargs via
`Annotated[T, pydantic.Field(description="...")]`. This is the canonical
pydantic pattern; a2kit reads the `FieldInfo` and forwards the description
to both the MCP input schema and click `--option HELP`.

```python
from typing import Annotated

import pydantic

@a2kit.read()
async def fetch(
    *,
    url: Annotated[str, pydantic.Field(description="Absolute http(s) URL.")],
    include_links: Annotated[
        bool,
        pydantic.Field(
            description=(
                "Include the extracted `links` array in the response. "
                "Default False, links are a large share of payload bytes "
                "on aggregator pages."
            ),
        ),
    ] = False,
) -> FetchResponse:
    """First line is the short description.

    The full body is the long help, markdown stripped on CLI, intact on MCP.
    """
```

Long descriptions are intentional, MCP agents read them via `list_tools` to
decide whether/how to call your tool. For kwargs that are Pydantic body
models, `Field(description=...)` already works inside the model declaration.

### Health probe

```python
app = a2kit.App("my-app")

@app.health_check
async def _sqlite() -> a2kit.HealthResult:
    return a2kit.HealthResult.ok() if state.sqlite else a2kit.HealthResult.fail("not opened")
```

The first `health_check` registration installs a built-in `_meta.health`
tool (hidden from agent-facing
`list_tools` but invokable by name). CLI exposes `<app> health` whose exit
code reflects aggregated status. The `_meta.*` namespace is reserved —
user tools can't claim it.

### Logging + progress + events + reports (`ToolContext`)

`a2kit.ToolContext` is an alias for `fastmcp.Context`. All Context logging
methods are async; field-bearing logging, events, and reports live as
free functions in `a2kit.ldd` (three siblings, one dispatch shape).

> **LDD** = *Logging / Data / Diagnostics* — the narrative-with-data
> primitives bundled together because they share a dispatch shape and a
> kill-switch.

| Channel | API | When to use |
|---|---|---|
| Plain logging (fastmcp passthrough) | `await ctx.info(msg)` / `ctx.info(msg, extra={"k": 1})` | Free-form messages to the MCP client; matches fastmcp's narrow signature |
| **Fielded logging (a2kit.ldd)** | `await info(ctx, msg, **fields)` (also `warning` / `error` / `debug` / `log`) | Structured narrative-with-data; renders identically on CLI and MCP. **Don't** pass kwargs to `ctx.info` directly — it crashes on MCP transport. |
| Numeric progress | `await ctx.report_progress(i, n)` | "30 of 100" — for progress bars |
| **Narrative events (kwargs)** | `await event(ctx, "name.string", **payload)` | Typed milestones agents pattern-match (e.g. `"api.fetched"`) |
| **Narrative events (typed)** | `await event(ctx, MyEvent(...))` — instance second positional | Pass a dataclass / pydantic model directly; name defaults to class name, fields serialize via `dataclasses.asdict` / `model_dump`. Enum fields coerced via `.value`. |
| **Typed reports** | `await report(ctx, payload)` (requires `reports=ReportT` kwarg on the verb decorator) | Mid-flight result chunks with a declared schema |
| **Typed event registry** | `app.ldd.events.register(MyEvent, progress=fn)` then `await app.ldd.events.emit_typed(ctx, evt)` | One-call emit: dump → event → progress (use this when you also need progress reporting) |

`info` / `warning` / `error` / `debug` / `log` also accept the instance
form (`await info(ctx, MyEvent(...))`) — same coercion rules as `event`,
shared helper so the two primitives can't drift.

```python
from pydantic import BaseModel
from a2kit.ldd import event, info, report


class BatchReport(BaseModel):
    batch: int
    accepted: int


@a2kit.write(reports=BatchReport)
async def bulk_import(*, ctx: a2kit.ToolContext, file: str) -> dict:
    await event(ctx, "import.started", file=file)
    items = await load(file)
    for i, item in enumerate(items):
        await ctx.report_progress(i, len(items))
        await info(ctx, "processing", batch=i, count=len(items))
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
emissions still type-validate `reports=` payloads — keeps tests
deterministic.

**Lint rule.** `A2K-LDD-REPORT-TYPE` fires when `report(ctx, ...)` is
called without a `reports=ReportT` kwarg on the verb decorator, or when
the declared type is defined inside a function (Pydantic forward-ref
constraint).

The `ctx` parameter is stripped from the input schema and from CLI
option generation.

## CLI

`a2kit.run(app)` exposes:

- `<app> --help` — top-level: one entry per Router (with progressive-disclosure hint), plus `schema`, `serve`, plus any subcommand attached via `app.add_cli(...)`.
- `<app> <router> --help` — list tools in that router.
- `<app> <router> <tool> [--name VALUE ...] [--format=auto|json|tsv|page-tsv] [--schema]` — invoke the tool in-process. Output flows through the formatter; `auto` picks based on the tool's return-type annotation (`list[ScalarOnlyModel]` → TSV, `Page[T]` → hybrid `page-tsv`, else JSON).
- `<app> connections {login,logout,list,show,delete}` — present iff the app wired `connections_cli(...)` via `add_cli`.
- `<app> schema [TOOL] [--format=auto|json|tsv] [--jsonl]` — schema discovery.
- `<app> serve [--transport=stdio|http] [--host] [--port] [--mcp-only|--rest-only]` — the server (the ONLY mode that loads fastmcp). `--transport=stdio` (default) serves MCP over a stdio pipe. `--transport=http` runs a **multiplexed server**: one process, one port, the MCP surface mounted under `/mcp` and the REST surface (health route + OpenAPI document) under `/api`. `--mcp-only` / `--rest-only` narrow it to a single surface (mutually exclusive; `--rest-only` requires `--transport=http`).

`'fastmcp' not in sys.modules` after any non-`serve` command — verified by `tests/test_cold_start.py`. uvicorn and the REST sub-app load only on `serve --transport=http`.

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

**Storage location.** Connections persist under `$A2KIT_CONFIG_HOME` if
set, otherwise `~/.config/a2kit/connections/`. One JSONL file per
`ConnectionConfig` subclass; each line is a saved record keyed by the
config's `Key` namedtuple.

Cloud-secret backends (AWS / Azure / GCP) compose via pydantic-settings sources — no a2kit-specific resolver registration needed.

## Errors

Typed errors live in the standalone [`a2effect`](packages/a2effect/)
package. Subclass `AppError`, annotate the return as
`Annotated[T, Raises(E1, E2)]`, and the framework renders the
envelope to MCP (`content` prose + `structuredContent.error` envelope),
HTTP (kind-mapped status + `{"error": <envelope>}` body), and CLI
(kind-mapped sysexits.h exit code + prose to stderr) without further
author input. Per-class `http_status` / `cli_exit_code` ClassVars
override the kind defaults (`NotFound` subclasses commonly set
`http_status = 404`; `Timeout` subclasses set `504`).

Register enrichers on the constructed router instance:

```python
router = MyRouter()

@router.enricher
def pg_enricher(exc: asyncpg.PostgresError) -> UpstreamUnavailable | None:
    return UpstreamUnavailable(str(exc))

app.add_router(router)
```

See [`packages/a2effect/README.md`](packages/a2effect/README.md) for
the quickstart, [`docs/MIGRATION_TYPED_ERRORS.md`](docs/MIGRATION_TYPED_ERRORS.md)
for the mechanical migration recipe, and
[`docs/adr/0021-typed-error-foundation.md`](docs/adr/0021-typed-error-foundation.md)
for the why.

## Lint

```bash
a2kit lint static src/
a2kit lint runtime --import myapp.server:app
```

Active rules:

- `A2K-CONN-LIST-PLACEHOLDER` — `${VAR}` inside list/dict fields on `ConnectionConfig`.
- `A2K-IMPORT-DISCIPLINE` — `fastmcp` imports outside `packages/mcp/` and the lazy-load lines in `packages/cli/builder.py`.
- `A2K-LDD-REPORT-TYPE` — `report(ctx, ...)` without a `reports=ReportT` kwarg on the verb decorator, or report type defined inside a function.
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
factories on an `a2kit.App`:

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

### Full-dispatch tests with `a2kit.testing.client`

For tests that should exercise the real dispatcher (DI resolution,
schema, ctx wiring, formatter), use `a2kit.testing.client(app)`:

```python
import a2kit
from a2kit.testing import client


async def test_full_dispatch() -> None:
    # Override a DI binding on a fresh App with the fake provided last.
    app = (
        a2kit.App("test")
        .add_router(TasksRouter())
        .provide(TrackerStore, FakeStore)
    )
    async with client(app) as c:
        # invoke → Python value
        value = await c.invoke("tasks.get", id="t1")
        # call_wire → formatter-encoded payload (JSON / TSV / page-tsv)
        wire = await c.call_wire("tasks.get", id="t1")
```

`c.invoke` returns the tool's Python return value. `c.call_wire` runs
the same call through the formatter the production transports use, so
`Page[T]`, TSV-encoded lists, and other type-driven format choices can
be pinned without spawning a server. Use `invoke` for value-shape
assertions, `call_wire` when the assertion needs the wire shape.

Test overrides are **re-build, not post-build mutation** (ADR 0019):
construct a fresh `a2kit.App` and `provide` the fake last
(last-write-wins). There is no `TestClient.override` — it was removed
because it mutated an already-built runtime container, contradicting
ADR 0006.

#### Async provider factories

`app.provide(T, factory)` accepts an `async def` factory. First
resolution awaits inside the dispatcher; subsequent resolves return the
cached value:

```python
async def build_pool(settings: AppSettings) -> Pool:
    pool = await Pool.open(settings.dsn)
    return pool

app.provide(Pool, build_pool)
```

#### Ambient LDD context

`a2kit.ldd.event` / `report` / `log` / `info` / `warning` / `error` /
`debug` read their `ctx` from a `ContextVar` set by the dispatcher.
Tool authors declare `ctx: a2kit.ToolContext` on the tool signature
and call the primitives with no `ctx` argument. Calling a primitive
outside an active dispatch (lifecycle hook, module-level code, or a
tool that omitted `ctx`) raises
`a2kit.exceptions.AmbientContextMissing`. See
[OPERATIONAL_CONTRACTS.md](OPERATIONAL_CONTRACTS.md) Q8.

## Migration from v0.x

a2kit is pre-1.0 with a fast release cadence — [CHANGELOG.md](CHANGELOG.md)
carries the full break history. The notes still relevant to a recent
consumer:

- `a2kit.AppBuilder(...).build()` → `a2kit.App(...)` — one type, no `build()`; a finisher seals it (ADR 0017, supersedes ADR 0016)
- `TestClient.override(T, fake)` → re-build: construct a fresh `a2kit.App` and `provide(T, fake)` last (last-write-wins)

Older breaks (the v0.19 → v0.20 thin-core cut, the v0.21–v0.33 surface
reshapes) are in `CHANGELOG.md`.

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
