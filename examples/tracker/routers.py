"""Two routers in one module — `projects` and `tasks`.

Both subclass `a2kit.Router`. The slug is auto-derived from the class name
(`ProjectsRouter` → `projects`, `TasksRouter` → `tasks`).

Verb decorator semantics:
- `@MyRouter.list()`  — many-out, list-view kit on (filter/fields/pagination), Cap.READ
- `@MyRouter.read()`  — single result, no list-view, Cap.READ
- `@MyRouter.write()` — mutation, Cap.WRITE, refuses on read-only connections

Each tool body declares its connection dependency via the v0.15
Annotated/Depends idiom: `*, conn: Annotated[TrackerConn, Depends(get_conn)]`.
The kit injects a `connection: str` kwarg on the published tool signature
(consumed by FastMCP / CLI), forwards it to `get_conn`, and passes the
resolved `TrackerConn` to the tool body.

The `enricher=` field is set ONCE on each Router class. Every tool inherits
it; no per-tool repetition. A tool that needs a different enricher can still
pass `enricher=` on its own decorator and that wins.

Note: this module deliberately does NOT use `from __future__ import annotations`.
The DI resolver inspects runtime annotations via
`typing.get_type_hints(include_extras=True)`; PEP 593 metadata (`Depends(...)`)
only survives that round-trip when annotations evaluate at runtime.
"""

import uuid
from typing import Annotated

import a2kit
from a2kit.di import Depends

from .connection import TrackerConn
from .deps import get_conn
from .enrichers import tracker_404_enricher
from .models import Project, Task
from .storage import TrackerStore


class ProjectsRouter(a2kit.Router):
    """Project-scoped tools. Slug: `projects`."""

    enricher: a2kit.EnricherFn | None = tracker_404_enricher


class TasksRouter(a2kit.Router):
    """Task-scoped tools. Slug: `tasks`."""

    enricher: a2kit.EnricherFn | None = tracker_404_enricher


# ---- Projects --------------------------------------------------------------- #


@ProjectsRouter.list()
async def list_projects(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[Project]:
    """List every project. Filter / fields / cursor are auto-injected by `@list()`."""
    projects, _ = TrackerStore(conn).load_state()
    return projects


@ProjectsRouter.read()
async def get_project(*, conn: Annotated[TrackerConn, Depends(get_conn)], project_id: str) -> Project:
    """Fetch one project by id."""
    projects, _ = TrackerStore(conn).load_state()
    for p in projects:
        if p.id == project_id:
            return p
    msg = f"project {project_id!r}"
    raise KeyError(msg)


@ProjectsRouter.write()
async def create_project(*, conn: Annotated[TrackerConn, Depends(get_conn)], name: str) -> Project:
    """Create a new project with `name`. Returns the created record."""
    store = TrackerStore(conn)
    projects, tasks = store.load_state()
    new = Project(id=str(uuid.uuid4())[:8], name=name)
    projects.append(new)
    store.replace(projects, tasks)
    return new


@ProjectsRouter.write()
async def archive_project(*, conn: Annotated[TrackerConn, Depends(get_conn)], project_id: str) -> Project:
    """Mark a project archived. Idempotent — archiving twice is a no-op."""
    store = TrackerStore(conn)
    projects, tasks = store.load_state()
    for i, p in enumerate(projects):
        if p.id == project_id:
            projects[i] = p.model_copy(update={"archived": True})
            store.replace(projects, tasks)
            return projects[i]
    msg = f"project {project_id!r}"
    raise KeyError(msg)


# ---- Tasks ------------------------------------------------------------------ #


@TasksRouter.list()
async def list_tasks(*, conn: Annotated[TrackerConn, Depends(get_conn)], project_id: str | None = None) -> list[Task]:
    """List tasks, optionally narrowed to one project.

    `project_id` is a *passthrough* param — it reaches the agent. The
    `filter` / `fields` / `cursor` knobs are kit-injected and don't show
    up here; they're applied automatically before the response goes back.
    """
    _, tasks = TrackerStore(conn).load_state()
    if project_id is not None:
        tasks = [t for t in tasks if t.project_id == project_id]
    return tasks


@TasksRouter.read()
async def get_task(*, conn: Annotated[TrackerConn, Depends(get_conn)], task_id: str) -> Task:
    """Fetch one task by id."""
    _, tasks = TrackerStore(conn).load_state()
    for t in tasks:
        if t.id == task_id:
            return t
    msg = f"task {task_id!r}"
    raise KeyError(msg)


@TasksRouter.write()
async def create_task(*, conn: Annotated[TrackerConn, Depends(get_conn)], project_id: str, title: str) -> Task:
    """Create a task under `project_id`. Validates the project exists first."""
    store = TrackerStore(conn)
    projects, tasks = store.load_state()
    if not any(p.id == project_id for p in projects):
        msg = f"project {project_id!r}"
        raise KeyError(msg)
    new = Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title)
    tasks.append(new)
    store.replace(projects, tasks)
    return new


@TasksRouter.write()
async def complete_task(*, conn: Annotated[TrackerConn, Depends(get_conn)], task_id: str) -> Task:
    """Mark a task done. Idempotent."""
    store = TrackerStore(conn)
    projects, tasks = store.load_state()
    for i, t in enumerate(tasks):
        if t.id == task_id:
            tasks[i] = t.model_copy(update={"done": True})
            store.replace(projects, tasks)
            return tasks[i]
    msg = f"task {task_id!r}"
    raise KeyError(msg)
