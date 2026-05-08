# tracker — the canonical a2kit demo

This is **the** example. It always reflects current best practices —
when `a2kit` evolves, this folder evolves with it.

What it demonstrates, in the order each idea shows up:

| File              | Surface demonstrated                                        |
|-------------------|-------------------------------------------------------------|
| `connection.py`   | `ConnectionConfig` subclass, token resolution (`${ENV}`)      |
| `models.py`       | Pydantic return models → auto-detected output format        |
| `storage.py`      | The connection's `db_path` IS the resource handle           |
| `enrichers.py`    | `(exc, tool_name) -> exc` rewrites for agent-readability    |
| `routers.py`      | `Router` subclasses, verb decorators, typed connection DI   |
| `server.py`       | Six-line composition root via `a2kit.App`                   |

## The author surface

`server.py` end-to-end:

```python
import a2kit
from .connection import TrackerConn
from .routers import ProjectsRouter, TasksRouter


def main() -> None:
    app = a2kit.App("tracker-mcp")
    app.connect(TrackerConn)
    app.use(ProjectsRouter)
    app.use(TasksRouter)
    app.run()
```

`routers.py` per-tool surface (one shape, repeated for every verb):

```python
class ProjectsRouter(a2kit.Router): ...

@ProjectsRouter.list()
async def list_projects(*, conn: TrackerConn) -> list[Project]: ...

@ProjectsRouter.read()
async def get_project(*, conn: TrackerConn, project_id: str) -> Project: ...

@ProjectsRouter.write(enricher=tracker_404_enricher)
async def create_project(*, conn: TrackerConn, name: str) -> Project: ...
```

That's it. No `@a2kit.tool(server=server, store=store, capabilities={Cap.READ}, ...)`
ceremony. The verb decorator picks the right capability set, the kit
auto-injects the connection, the list-view kit (filter/fields/cursor) is
on by default for `@list()` and off for `@read()` / `@write()`.

## What the kit does for you

| Feature                       | What you wrote                                | Without the kit                                                 |
|-------------------------------|-----------------------------------------------|------------------------------------------------------------------|
| Connection lookup             | `*, conn: TrackerConn`                        | parse arg, load file, resolve env vars, check read-only         |
| Capability tagging            | nothing — verb implies them                   | `capabilities={Cap.READ}` per tool, manually                    |
| List-view kit                 | `@TasksRouter.list()`                         | implement `filter` / `fields` / `cursor` per tool               |
| OTel spans                    | nothing — verbs enable them                   | `with tracer.start_as_current_span(...)` per call               |
| Write enforcement             | nothing — verb implies it                     | check `read_only` flag, raise `WriteNotAllowed`                 |
| Token resolution              | nothing — connection load handles it          | scan fields, dispatch on `${...}` / `op://`, call resolver      |
| Error enrichment              | `enricher=tracker_404_enricher`               | wrap every tool body in try/except                              |
| CLI commands                  | nothing — `app.run()` builds them             | hand-roll Click group with login/logout/connections/serve       |
| Output format                 | annotate `-> list[Project]`                   | choose JSON/TOON/TSV, encode, set MIME type                     |

## Try it

```bash
# Help — lists subcommands (serve, login, logout, connections, plus each tool)
uv run python -m examples.tracker.server

# Save a connection (the JSONL file is created lazily on first write)
uv run python -m examples.tracker.server login default db_path=/tmp/tracker.jsonl

# Invoke tools directly from the CLI — no MCP client needed
uv run python -m examples.tracker.server create_project connection=default name="ship v0.12"
uv run python -m examples.tracker.server list_projects connection=default
uv run python -m examples.tracker.server create_task connection=default project_id=<id> title="finish DI"

# Run as MCP server — stdio (default)
uv run python -m examples.tracker.server serve

# Or HTTP transport
uv run python -m examples.tracker.server serve --http :8080

# Default-select drops writes; opt in with --select
uv run python -m examples.tracker.server serve --select "default and tasks"
uv run python -m examples.tracker.server serve --select "default or write"
```

## Token resolution

The `token` field on `TrackerConn` accepts:

- A plain string — passes through unchanged.
- `${ENV_VAR}` — looked up in `os.environ` before the tool body runs.
- `op://<vault>/<item>/<field>` — resolved via 1Password CLI when available.

Save once, the kit handles substitution on every call:

```bash
uv run python -m examples.tracker.server login prod \
    db_path=/tmp/tracker-prod.jsonl \
    token='${TRACKER_TOKEN}'
```

## Read-only mode

```bash
uv run python -m examples.tracker.server login readonly db_path=/tmp/r.jsonl read_only=true
```

Calls to `create_project` / `complete_task` / `archive_project` against
the `readonly` connection raise `WriteNotAllowed` before the tool body
runs. No code in the example handles this — the kit does, because the
verbs are tagged `write=True`.

## Multiple routers

`ProjectsRouter` and `TasksRouter` are independent. `--select` controls
which ones serve:

```bash
# Only project tools (tasks router excluded)
uv run python -m examples.tracker.server serve --select "projects"

# Both, but no destructive ops
uv run python -m examples.tracker.server serve --select "default and not destructive"
```

## What's NOT in this example

- Custom DI providers — the connection is the only injected type today.
  Future a2kit versions add chained-provider DI (`*, store: TrackerStore`
  resolved from `TrackerConn` via a registered factory). When that lands,
  this example grows a `providers.py` module.
- Cassette-based testing — see `tests/test_cassettes.py` in the kit
  itself for how to record/replay HTTP without a real backend.
- Schema snapshots — flip `snapshot_dir=Path(...)` on either Router to
  freeze response shapes against drift.
