"""Tracker routers — typed per-call DI; class-attribute enrichers.

Tools declare ``store: TrackerStore`` directly; the App's container
resolves it from the wire ``connection`` value through the chain
``TrackerConn`` (auto-registered by ``connections_cli``) →
``TrackerStore`` (provided via ``app.provide(TrackerStore)``). The router
needs no ``__init__`` — it's just a class with tools.
"""

from __future__ import annotations

import asyncio
import uuid

import a2kit
from a2kit.packages.mcp.reports import reports

from .enrichers import tracker_404_enricher
from .models import BatchReport, Project, Task
from .store import TrackerStore


class ProjectsRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]  # noqa: RUF012

    @a2kit.list_("id", "name", "archived")
    async def list_projects(self, *, store: TrackerStore) -> list[Project]:
        projects, _ = store.load_state()
        return projects

    @a2kit.read()
    async def get_project(self, *, store: TrackerStore, project_id: str) -> Project:
        projects, _ = store.load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write()
    async def create_project(self, *, store: TrackerStore, name: str) -> Project:
        projects, tasks = store.load_state()
        new = Project(id=str(uuid.uuid4())[:8], name=name)
        projects.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def archive_project(self, *, store: TrackerStore, project_id: str) -> Project:
        projects, tasks = store.load_state()
        for i, p in enumerate(projects):
            if p.id == project_id:
                projects[i] = p.model_copy(update={"archived": True})
                store.replace(projects, tasks)
                return projects[i]
        raise KeyError(project_id)


class TasksRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]  # noqa: RUF012

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

    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task:
        _, tasks = store.load_state()
        for t in tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    @a2kit.write()
    async def create_task(self, *, store: TrackerStore, project_id: str, title: str) -> Task:
        projects, tasks = store.load_state()
        if not any(p.id == project_id for p in projects):
            raise KeyError(project_id)
        new = Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title)
        tasks.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def complete_task(self, *, store: TrackerStore, task_id: str) -> Task:
        projects, tasks = store.load_state()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                tasks[i] = t.model_copy(update={"done": True})
                store.replace(projects, tasks)
                return tasks[i]
        raise KeyError(task_id)

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
        """Import a batch of tasks; demonstrates all four LDD channels."""
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
            await asyncio.sleep(0)

        store.replace(projects, tasks)
        await ctx.event("import.complete", accepted=accepted, rejected=rejected)
        return {"accepted": accepted, "rejected": rejected}
