# tracker — the canonical a2kit demo

This is **the** example. It always reflects current best practices —
when `a2kit` evolves, this folder evolves with it.

| File              | Surface demonstrated                                                          |
|-------------------|-------------------------------------------------------------------------------|
| `connection.py`   | `ConnectionConfig` subclass; eager `${ENV}` / `op://` resolution              |
| `models.py`       | Pydantic return models + `BatchReport` (typed LDD report shape)               |
| `store.py`        | Plain class; `__init__` takes a `TrackerConn`                                 |
| `enrichers.py`    | `(exc, tool_name) -> exc` rewrites for agent-readability                      |
| `routers.py`      | Constructor injection + stacked `@enriches/@lists/@reports`, four LDD channels |
| `server.py`       | Composition root: `add_router` + `add_cli`, `a2kit.run(app)` entrypoint       |

## The author surface

`server.py` end-to-end:

```python
import a2kit
from a2kit.packages.connections import ConnectionStore, connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

_conn_store = ConnectionStore(TrackerConn)


async def get_store(connection: str) -> TrackerStore:
    conn = await _conn_store.load((connection,))
    return TrackerStore(conn)


app = a2kit.App("tracker-mcp")
app.add_router(ProjectsRouter(get_store))
app.add_router(TasksRouter(get_store))
app.add_cli(connections_cli(TrackerConn))


def main() -> None:
    a2kit.run(app)
```

That's the whole composition root. Three named verbs. No `Depends(...)`
sentinel, no plugin protocol, no class-as-key.

`routers.py` per-tool surface — constructor injection + stacked feature decorators:

```python
from a2kit.packages.enrichers import enriches


class ProjectsRouter(a2kit.Router):
    name = "projects"  # explicit slug (no auto-derivation)

    def __init__(self, get_store) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.read()
    @enriches(tracker_404_enricher)
    async def get_project(self, *, connection: str, project_id: str) -> Project:
        projects, _ = (await self.get_store(connection)).load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write()
    @enriches(tracker_404_enricher)
    async def archive_project(self, *, connection: str, project_id: str) -> Project:
        store = await self.get_store(connection)
        projects, tasks = store.load_state()
        ...
```

The framework sees `connection: str` and `project_id: str` as the user
input parameters, generates `--connection` and `--project-id` Click
options, and exposes the same shape over MCP. No introspection of
parameter defaults — `self.get_store` is a regular Python attribute.

## Listview kit — projection / pagination / selectable fields

`list_tasks` stacks `@lists(...)` on the verb decorator; the middleware
projects, paginates, and filters on the agent's behalf:

```python
from a2kit.packages.mcp.lists import lists


class TasksRouter(a2kit.Router):
    name = "tasks"

    @a2kit.list_()
    @lists(
        default_fields=("id", "title", "status", "assignee"),
        page_size=20,
        selectable_fields=("id", "title", "status", "assignee", "priority", ...),
    )
    @enriches(tracker_404_enricher)
    async def list_tasks(self, *, connection: str, project_id: str | None = None) -> list[Task]:
        _, tasks = (await self.get_store(connection)).load_state()
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks
```

Agents can override at call time:

- `--fields=id,title,priority` — pick a subset.
- `--page-size=5 --cursor=...` — paginate.
- `--filter='priority=="high" && !done'` — narrow with CEL.

## LDD — narrate what's happening, mid-flight

`bulk_import_tasks` exercises all four `ToolContext` channels:

```python
from a2kit.packages.mcp.reports import reports


@a2kit.write()
@reports(BatchReport)
@enriches(tracker_404_enricher)
async def bulk_import_tasks(
    self,
    *,
    ctx: a2kit.ToolContext,
    connection: str,
    project_id: str,
    titles: list[str],
    batch_size: int = 5,
) -> dict[str, int]:
    await ctx.event("import.started", project_id=project_id, n=len(titles))
    store = await self.get_store(connection)
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
[ +0.000 event   ] import.started project_id='abc12345' n=3
[ +0.002 INFO    ] loaded state projects=1 tasks=0
[ +0.002 progress] current=0 total=3
[ +0.003 report  ] BatchReport batch=0 accepted=3 rejected=0 project_id='abc12345'
[ +0.004 event   ] import.complete accepted=3 rejected=0
{"accepted":3,"rejected":0}
```

Top-level flags `--no-reports` / `--no-events` silence those channels;
`A2KIT_LDD=off` env disables both process-wide.

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
