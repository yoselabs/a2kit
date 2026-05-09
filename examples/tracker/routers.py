"""Tracker routers — constructor injection, per-tool enricher.

Routers receive a `get_store` factory in `__init__` and call it from each
tool method. No DI sentinel, no class-as-key, no Generic introspection.
The per-tool ``enricher=`` decorator kwarg attaches the not-found rewrite.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import a2kit
from a2kit.metadata import ListViewSettings

from .enrichers import tracker_404_enricher
from .models import BatchReport, Project, Task

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .store import TrackerStore

    GetStore = Callable[[str], Awaitable[TrackerStore]]


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


class ProjectsRouter(a2kit.Router):
    def __init__(self, get_store: GetStore) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.list_(enricher=tracker_404_enricher)
    async def list_projects(self, *, connection: str) -> list[Project]:
        projects, _ = (await self.get_store(connection)).load_state()
        return projects

    @a2kit.read(enricher=tracker_404_enricher)
    async def get_project(self, *, connection: str, project_id: str) -> Project:
        projects, _ = (await self.get_store(connection)).load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write(enricher=tracker_404_enricher)
    async def create_project(self, *, connection: str, name: str) -> Project:
        store = await self.get_store(connection)
        projects, tasks = store.load_state()
        new = Project(id=str(uuid.uuid4())[:8], name=name)
        projects.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write(enricher=tracker_404_enricher)
    async def archive_project(self, *, connection: str, project_id: str) -> Project:
        store = await self.get_store(connection)
        projects, tasks = store.load_state()
        for i, p in enumerate(projects):
            if p.id == project_id:
                projects[i] = p.model_copy(update={"archived": True})
                store.replace(projects, tasks)
                return projects[i]
        raise KeyError(project_id)


class TasksRouter(a2kit.Router):
    def __init__(self, get_store: GetStore) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.list_(list_view=_TASK_LIST_VIEW, enricher=tracker_404_enricher)
    async def list_tasks(self, *, connection: str, project_id: str | None = None) -> list[Task]:
        _, tasks = (await self.get_store(connection)).load_state()
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks

    @a2kit.read(enricher=tracker_404_enricher)
    async def get_task(self, *, connection: str, task_id: str) -> Task:
        _, tasks = (await self.get_store(connection)).load_state()
        for t in tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    @a2kit.write(enricher=tracker_404_enricher)
    async def create_task(self, *, connection: str, project_id: str, title: str) -> Task:
        store = await self.get_store(connection)
        projects, tasks = store.load_state()
        if not any(p.id == project_id for p in projects):
            raise KeyError(project_id)
        new = Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title)
        tasks.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write(enricher=tracker_404_enricher)
    async def complete_task(self, *, connection: str, task_id: str) -> Task:
        store = await self.get_store(connection)
        projects, tasks = store.load_state()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                tasks[i] = t.model_copy(update={"done": True})
                store.replace(projects, tasks)
                return tasks[i]
        raise KeyError(task_id)

    @a2kit.write(report=BatchReport, enricher=tracker_404_enricher)
    async def bulk_import_tasks(
        self,
        *,
        ctx: a2kit.ToolContext,
        connection: str,
        project_id: str,
        titles: list[str],
        batch_size: int = 5,
    ) -> dict[str, int]:
        """Import a batch of tasks; demonstrates all four LDD channels."""
        await ctx.event("import.started", project_id=project_id, n=len(titles))
        store = await self.get_store(connection)
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
            await asyncio.sleep(0)

        store.replace(projects, tasks)
        await ctx.event("import.complete", accepted=accepted, rejected=rejected)
        return {"accepted": accepted, "rejected": rejected}
