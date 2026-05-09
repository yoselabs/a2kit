"""Tracker routers — canonical demonstration of the v1.0 a2kit surface.

Patterns shown:

- ``Depends(TrackerConn)`` and ``Depends(TrackerStore)`` — class as the
  injection key. No stub ``get_conn`` function; no ``app.use_factory(...)``
  required for the common case.
- ``class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):`` —
  PEP 487 class kwarg captures the router-level enricher. No
  ``staticmethod(...)`` boilerplate.
- ``@a2kit.list_(list_view=ListViewSettings(...))`` — listview kit:
  ``default_fields`` projection, ``page_size`` pagination, and
  ``selectable_fields`` whitelist. The middleware applies these post-hoc
  on the in-memory list returned by the tool.
- ``@a2kit.write(report=BatchReport)`` + ``ctx.event`` /
  ``ctx.report`` / ``ctx.info`` / ``ctx.report_progress`` — all four LDD
  channels working together inside ``bulk_import_tasks``.
"""

from __future__ import annotations

import asyncio
import uuid

from uncalled_for import Depends

import a2kit
from a2kit.metadata import ListViewSettings

from .enrichers import tracker_404_enricher
from .models import BatchReport, Project, Task
from .store import TrackerStore


class ProjectsRouter(a2kit.Router, enricher=tracker_404_enricher):
    @a2kit.list_()
    async def list_projects(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
    ) -> list[Project]:
        projects, _ = store.load_state()
        return projects

    @a2kit.read()
    async def get_project(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str,
    ) -> Project:
        projects, _ = store.load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write()
    async def create_project(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        name: str,
    ) -> Project:
        projects, tasks = store.load_state()
        new = Project(id=str(uuid.uuid4())[:8], name=name)
        projects.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def archive_project(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str,
    ) -> Project:
        projects, tasks = store.load_state()
        for i, p in enumerate(projects):
            if p.id == project_id:
                projects[i] = p.model_copy(update={"archived": True})
                store.replace(projects, tasks)
                return projects[i]
        raise KeyError(project_id)


# ListView kit: project a wide model down to agent-friendly defaults, paginate,
# and let the agent opt into specific fields. The middleware applies these
# post-hoc on the in-memory result. With `pushdown-listview` (queued change),
# these kwargs translate to underlying SQL/JQL/REST parameters automatically.
_TASK_LIST_VIEW = ListViewSettings(
    default_fields=("id", "title", "status", "assignee"),
    page_size=20,
    selectable_fields=(
        "id",
        "title",
        "status",
        "assignee",
        "priority",
        "project_id",
        "created_at",
        "done",
    ),
)


class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):
    @a2kit.list_(list_view=_TASK_LIST_VIEW)
    async def list_tasks(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str | None = None,
    ) -> list[Task]:
        """List tasks, optionally scoped to one project.

        Listview kwargs (``--fields``, ``--page-size``, ``--cursor``,
        ``--filter``) flow through the middleware — try
        ``--filter='priority=="high" && !done'`` to narrow, or
        ``--fields=id,title`` to project. The tool body returns the full list;
        the middleware does the rest.
        """
        _, tasks = store.load_state()
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks

    @a2kit.read()
    async def get_task(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        task_id: str,
    ) -> Task:
        _, tasks = store.load_state()
        for t in tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    @a2kit.write()
    async def create_task(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str,
        title: str,
    ) -> Task:
        projects, tasks = store.load_state()
        if not any(p.id == project_id for p in projects):
            raise KeyError(project_id)
        new = Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title)
        tasks.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def complete_task(
        self,
        *,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        task_id: str,
    ) -> Task:
        projects, tasks = store.load_state()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                tasks[i] = t.model_copy(update={"done": True})
                store.replace(projects, tasks)
                return tasks[i]
        raise KeyError(task_id)

    @a2kit.write(report=BatchReport)
    async def bulk_import_tasks(
        self,
        *,
        ctx: a2kit.ToolContext,
        store: TrackerStore = Depends(TrackerStore),
        connection: str,
        project_id: str,
        titles: list[str],
        batch_size: int = 5,
    ) -> dict[str, int]:
        """Import a batch of tasks, demonstrating all four LDD channels.

        Channels exercised:
        - ``ctx.event(name, ...)`` — milestones (``import.started`` /
          ``import.complete``) the agent can pattern-match.
        - ``ctx.info(...)`` — free-form telemetry.
        - ``await ctx.report_progress(i, n)`` — numeric progress for bars.
        - ``await ctx.report(BatchReport(...))`` — typed mid-flight chunks
          declared via ``report=BatchReport`` on the decorator. The agent
          receives structured payloads, not parsed log lines.
        """
        await ctx.event("import.started", project_id=project_id, n=len(titles))
        projects, tasks = store.load_state()
        if not any(p.id == project_id for p in projects):
            raise KeyError(project_id)
        ctx.info("loaded state", projects=len(projects), tasks=len(tasks))

        accepted = 0
        rejected = 0
        for i in range(0, len(titles), batch_size):
            chunk = titles[i : i + batch_size]
            await ctx.report_progress(i, len(titles))
            batch_accepted = 0
            batch_rejected = 0
            for title in chunk:
                if not title.strip():
                    batch_rejected += 1
                    continue
                tasks.append(Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title.strip()))
                batch_accepted += 1
            accepted += batch_accepted
            rejected += batch_rejected
            await ctx.report(
                BatchReport(
                    batch=i // batch_size,
                    accepted=batch_accepted,
                    rejected=batch_rejected,
                    project_id=project_id,
                )
            )
            # Yield so progress streams perceptibly even on small inputs.
            await asyncio.sleep(0)

        store.replace(projects, tasks)
        await ctx.event("import.complete", accepted=accepted, rejected=rejected)
        return {"accepted": accepted, "rejected": rejected}
