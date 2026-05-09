# tracker — the canonical a2kit demo

This is **the** example. It always reflects current best practices —
when `a2kit` evolves, this folder evolves with it.

What it demonstrates, in the order each idea shows up:

| File              | Surface demonstrated                                              |
|-------------------|-------------------------------------------------------------------|
| `connection.py`   | `ConnectionConfig` subclass (`a2kit.packages.connections`); eager `${ENV}` / `op://` resolution |
| `models.py`       | Pydantic return models → auto-detected output format              |
| `storage.py`      | The connection's `db_path` IS the resource handle                 |
| `enrichers.py`    | `(exc, tool_name) -> exc` rewrites for agent-readability          |
| `deps.py`         | Stable `get_conn` identity for `Depends(get_conn)` references     |
| `routers.py`      | `Router` subclasses, verb decorators, parameter-default `Depends` |
| `server.py`       | Composition root: `a2kit.App` + `a2kit.run(app)` entrypoint       |

## The author surface

`server.py` end-to-end:

```python
import a2kit
from a2kit.packages.connections import get_conn_factory

from .connection import TrackerConn
from .deps import get_conn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)
app.use(ProjectsRouter())
app.use(TasksRouter())


def main() -> None:
    a2kit.run(app)
```

`routers.py` per-tool surface (one shape, repeated for every verb):

```python
from uncalled_for import Depends

from .deps import get_conn

class ProjectsRouter(a2kit.Router):
    enricher = staticmethod(tracker_404_enricher)

    @a2kit.list_()
    async def list_projects(self, *, conn: TrackerConn = Depends(get_conn)) -> list[Project]: ...

    @a2kit.read()
    async def get_project(self, *, conn: TrackerConn = Depends(get_conn), project_id: str) -> Project: ...

    @a2kit.write()
    async def create_project(self, *, conn: TrackerConn = Depends(get_conn), name: str) -> Project: ...
```

That's it. No `@a2kit.tool(server=server, store=store, capabilities={Cap.READ}, ...)`
ceremony. The verb decorator picks the right `ToolAnnotations` + tag set,
`Depends(get_conn)` resolves the connection, and the per-Router `enricher`
wraps every tool's exception path.

## What the kit does for you

| Feature                 | What you wrote                                       | Without the kit                                              |
|-------------------------|------------------------------------------------------|--------------------------------------------------------------|
| Connection lookup       | `*, conn: TrackerConn = Depends(get_conn)`           | parse arg, load file, resolve env vars, check read-only      |
| Tag-based capabilities  | nothing — verb sets the tag                          | `tags={"read","write"}` per tool, manually                   |
| OTel-friendly surface   | nothing — `tags` flow through fastmcp                | per-tool span management                                     |
| Write enforcement       | `@a2kit.write()` + `read_only` field                 | check `read_only`, raise `WriteNotAllowed`                   |
| Token resolution        | `db_path: str` / `token: str` on `ConnectionConfig`  | scan fields, dispatch on `${...}` / `op://`, call resolver   |
| Error enrichment        | `enricher = staticmethod(tracker_404_enricher)`      | wrap every tool body in try/except                           |
| CLI commands            | nothing — `a2kit.run(app)` builds them               | hand-roll Click group with login/logout/connections/serve    |
| Output format           | annotate `-> list[Project]`                          | choose JSON/TOON, encode, set MIME type                      |

## Try it

```bash
# Help — lists routers, connections, schema, serve
uv run python -m examples.tracker.server --help

# Save a connection (the JSONL file is created lazily on first write)
uv run python -m examples.tracker.server connections login tracker --field db_path=/tmp/tracker.jsonl

# Invoke tools directly from the CLI — no MCP client needed
uv run python -m examples.tracker.server projects create-project --name "ship v1.0"
uv run python -m examples.tracker.server projects list-projects
uv run python -m examples.tracker.server tasks create-task --project-id <id> --title "finish DI"

# Per-tool schema dump (TOON by default; --format=json for JSON Schema tooling)
uv run python -m examples.tracker.server schema list_tasks
uv run python -m examples.tracker.server schema list_tasks --format=json

# Run as MCP server — stdio (default; only this loads fastmcp)
uv run python -m examples.tracker.server serve

# Or HTTP transport
uv run python -m examples.tracker.server serve --transport=http --port 8080
```

## Token resolution (eager)

The `token` field on `TrackerConn` accepts:

- A plain string — passes through unchanged.
- `${ENV_VAR}` — looked up in `os.environ` at `store.load(...)` time.
- `op://<vault>/<item>/<field>` — resolved via the 1Password CLI at load time.

Eager resolution means missing env vars / unreachable secrets fail fast at
load — not on first tool call. Round-trip preserves placeholders:
`store.save(cfg)` writes the original `${ENV_VAR}`, never the resolved
value.

```bash
uv run python -m examples.tracker.server connections login tracker \
    --field db_path=/tmp/tracker-prod.jsonl \
    --field 'token=${TRACKER_TOKEN}'
```

## Read-only mode

```bash
uv run python -m examples.tracker.server connections login readonly \
    --field db_path=/tmp/r.jsonl --field read_only=true
```

Calls to `create_project` / `complete_task` / `archive_project` against
the `readonly` connection raise `WriteNotAllowed` before the tool body
runs.

## Test override pattern

```python
from a2kit.packages.testing import make_test_app

from examples.tracker.deps import get_conn
from examples.tracker.routers import TasksRouter

def fake_get_conn(*, connection: str):
    async def _factory(*, connection):
        return TrackerConn(db_path="/tmp/test.jsonl")
    return _factory

def test_create_task():
    app = make_test_app([TasksRouter()], overrides={get_conn: fake_get_conn})
    # ... invoke through app.tools()
```

There is no `app.dependency_overrides` map — `make_test_app` rebuilds the
tool fns with `Depends(fake)` patched in via `uncalled_for` primitives.
