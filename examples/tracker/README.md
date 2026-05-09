# tracker — the canonical a2kit demo

This is **the** example. It always reflects current best practices —
when `a2kit` evolves, this folder evolves with it.

What it demonstrates, in the order each idea shows up:

| File              | Surface demonstrated                                              |
|-------------------|-------------------------------------------------------------------|
| `connection.py`   | `ConnectionConfig` subclass; eager `${ENV}` / `op://` resolution  |
| `models.py`       | Pydantic return models + `BatchReport` (typed LDD report shape)   |
| `store.py`        | `a2kit.Store[TrackerConn]` — Generic binds the conn type          |
| `enrichers.py`    | `(exc, tool_name) -> exc` rewrites for agent-readability          |
| `routers.py`      | `Depends(<class>)` injection, listview kit, all four LDD channels |
| `server.py`       | Composition root: `a2kit.App` + `a2kit.run(app)` entrypoint       |

## The author surface

`server.py` end-to-end:

```python
import a2kit

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
app.use(ProjectsRouter())
app.use(TasksRouter())


def main() -> None:
    a2kit.run(app)
```

That's the whole composition root. No stub `get_conn` function. No
`app.use_factory(...)`. The store class declares its conn binding via
`class TrackerStore(a2kit.Store[TrackerConn]):` and the runtime composes
conn → store at call time.

`routers.py` per-tool surface — three injection shapes, one rule:

```python
from uncalled_for import Depends

class ProjectsRouter(a2kit.Router, enricher=tracker_404_enricher):
    # Inject the conn directly.
    @a2kit.read()
    async def get_project(
        self, *,
        conn: TrackerConn = Depends(TrackerConn),
        connection: str,
        project_id: str,
    ) -> Project: ...

    # Inject the store (composes conn → store).
    @a2kit.write()
    async def archive_project(
        self, *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str,
    ) -> Project:
        projects, tasks = store.load_state()
        ...
```

The enricher reads as a class kwarg — no `staticmethod(...)` wrapper.

## Listview kit — projection / pagination / selectable fields

`list_tasks` declares `list_view=ListViewSettings(...)` so the middleware
projects, paginates, and filters on the agent's behalf:

```python
_TASK_LIST_VIEW = ListViewSettings(
    default_fields=("id", "title", "status", "assignee"),
    page_size=20,
    selectable_fields=("id", "title", "status", "assignee", "priority", ...),
)

class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):
    @a2kit.list_(list_view=_TASK_LIST_VIEW)
    async def list_tasks(
        self, *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str | None = None,
    ) -> list[Task]:
        _, tasks = store.load_state()
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks
```

Agents can override at call time:

- `--fields=id,title,priority` — pick a subset.
- `--page-size=5 --cursor=...` — paginate.
- `--filter='priority=="high" && !done'` — narrow with CEL.

The middleware applies these post-hoc. The queued `pushdown-listview`
change will translate the same kwargs into native SQL/JQL/REST
parameters when the underlying service supports it — without touching
the tool body.

## LDD — narrate what's happening, mid-flight

`bulk_import_tasks` exercises all four `ToolContext` channels:

```python
@a2kit.write(report=BatchReport)
async def bulk_import_tasks(
    self, *,
    ctx: a2kit.ToolContext,
    store: TrackerStore = Depends(TrackerStore),
    connection: str,
    project_id: str,
    titles: list[str],
    batch_size: int = 5,
) -> dict[str, int]:
    await ctx.event("import.started", project_id=project_id, n=len(titles))
    projects, tasks = store.load_state()
    ctx.info("loaded state", projects=len(projects), tasks=len(tasks))
    for i in range(0, len(titles), batch_size):
        ...
        await ctx.report_progress(i, len(titles))
        await ctx.report(BatchReport(batch=..., accepted=..., rejected=...))
    await ctx.event("import.complete", accepted=N, rejected=M)
    return {"accepted": N, "rejected": M}
```

CLI invocation shows the four channels interleaved on stderr:

```
[ +0.001 event   ] import.started project_id='abc12345' n=3
[ +0.001 INFO    ] loaded state projects=1 tasks=0
[ +0.001 progress] current=0 total=3
[ +0.003 report  ] BatchReport batch=0 accepted=2 rejected=0 project_id='abc12345'
[ +0.003 progress] current=2 total=3
[ +0.003 report  ] BatchReport batch=1 accepted=1 rejected=0 project_id='abc12345'
[ +0.004 event   ] import.complete accepted=3 rejected=0
{"accepted":3,"rejected":0}
```

Top-level flags `--no-reports` / `--no-events` silence those channels;
`A2KIT_LDD=off` env disables both process-wide.

## Why no `get_conn` stub?

The v1.0 baseline required:

```python
# Stub function — never called, just an identity.
async def get_conn(*, connection: str) -> TrackerConn: ...

# Composition root wires the real factory:
app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)
```

This change collapses three identifiers into one. `Depends(TrackerConn)`
*is* the contract — the runtime sees a registered conn class, looks up
the loader, reads `connection: str` from the tool kwargs, and injects.
The legacy stub-factory shape still works (useful for multi-tenant
factory swaps, test overrides), but the simple case no longer needs it.

## Try it

```bash
# Help — lists routers, connections, schema, serve
uv run python -m examples.tracker.server --help

# Save a connection
uv run python -m examples.tracker.server connections login TrackerConn \
    --key=default --field db_path=/tmp/tracker.jsonl

# Invoke tools — note the required `--connection=<name>` kwarg
uv run python -m examples.tracker.server projects create_project \
    --connection=default --name "Demo"
uv run python -m examples.tracker.server projects list_projects --connection=default

# LDD demo — interleaved stderr + final stdout
uv run python -m examples.tracker.server tasks bulk_import_tasks \
    --connection=default --project-id=<id> --titles='["a","b","c"]'

# Per-tool schema dump
uv run python -m examples.tracker.server schema list_tasks
uv run python -m examples.tracker.server schema bulk_import_tasks --format=json

# Run as MCP server (the only mode that loads fastmcp)
uv run python -m examples.tracker.server serve --transport=stdio
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

## Read-only mode

```bash
uv run python -m examples.tracker.server connections login TrackerConn \
    --key=readonly --field db_path=/tmp/r.jsonl --field read_only=true
```

Calls to `create_project` / `complete_task` / `archive_project` against
the `readonly` connection raise `WriteNotAllowed` before the tool body
runs.
