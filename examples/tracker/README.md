# tracker — the canonical a2kit demo

This is **the** example. It always reflects current best practices —
when `a2kit` evolves, this folder evolves with it.

| File              | Surface demonstrated                                                          |
|-------------------|-------------------------------------------------------------------------------|
| `connection.py`   | `ConnectionConfig` subclass; eager `${ENV}` / `op://` resolution              |
| `models.py`       | Pydantic return models + `BatchReport` (typed LDD report shape)               |
| `store.py`        | Plain class; `__init__(self, conn: TrackerConn)` — class-as-factory ready     |
| `enrichers.py`    | Pure `(exc) -> str \| None` enricher; class-attribute `enrichers` on routers  |
| `routers.py`      | Typed kwargs `store: TrackerStore`, `enrichers = [...]`, four LDD channels    |
| `server.py`       | Composition root: `add_router` + `provide` + `add_cli`, `a2kit.run(app)`      |

## The author surface

`server.py` end-to-end:

```python
import a2kit
from a2kit.packages.connections import connections_cli

from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter
from .store import TrackerStore

app = (
    a2kit.App("tracker-mcp")
    .add_router(ProjectsRouter())
    .add_router(TasksRouter())
    .provide(TrackerStore)                   # class-as-factory; container reads __init__
    .add_cli(connections_cli(TrackerConn))   # auto-installs TrackerConn provider
)


def main() -> None:
    a2kit.run(app)
```

That's the whole composition root. Two `provide()`-flavored DI calls
(one explicit, one auto-installed by the connections CLI) plus three
named verbs. No `Depends(...)` sentinel, no plugin protocol, no
class-as-key.

`routers.py` per-tool surface — typed kwargs + class-attribute enrichers:

```python
from .enrichers import tracker_404_enricher
from .store import TrackerStore


class ProjectsRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]
    # name auto-derived from class name → "projects"

    @a2kit.read()
    async def get_project(self, *, store: TrackerStore, project_id: str) -> Project:
        projects, _ = store.load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write()
    async def archive_project(self, *, store: TrackerStore, project_id: str) -> Project:
        projects, tasks = store.load_state()
        ...
```

The framework reads the wire `connection` arg, resolves it through the
auto-installed `TrackerConn` provider, then constructs `TrackerStore`
via its `__init__(self, conn: TrackerConn)` and binds it to the `store`
kwarg. The wire schema strips `store` — agents see only `connection` +
`project_id`. The class-attribute `enrichers` runs on any exception the
tool raises and rewrites the user-facing message.

## Listview kit — projection / pagination / selectable fields

`list_tasks` declares its projection inline on the consolidated
`@a2kit.list_(...)`; the middleware projects, paginates, and filters
on the agent's behalf. Selectable fields are derived from the
`list[Task]` return annotation — no redundant enumeration.

```python
class TasksRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]
    # name auto-derived → "tasks"

    @a2kit.list_("id", "title", "done", "assignee", page_size=20)
    async def list_tasks(
        self,
        *,
        store: TrackerStore,
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

## LDD — narrate what's happening, mid-flight

`bulk_import_tasks` exercises all four `ToolContext` channels:

```python
from a2kit.packages.mcp.reports import reports


@a2kit.write()
@reports(BatchReport)
async def bulk_import_tasks(
    self,
    *,
    ctx: a2kit.ToolContext,
    store: TrackerStore,
    project_id: str,
    titles: list[str],
    batch_size: int = 5,
) -> dict[str, int]:
    await event(ctx, "import.started", project_id=project_id, n=len(titles))
    projects, tasks = store.load_state()
    await info(ctx, "loaded state", projects=len(projects), tasks=len(tasks))
    for i in range(0, len(titles), batch_size):
        ...
        await ctx.report_progress(i, len(titles))
        await report(ctx, BatchReport(batch=..., accepted=..., rejected=...))
    await event(ctx, "import.complete", accepted=N, rejected=M)
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
