from __future__ import annotations

import uuid

from uncalled_for import Depends

import a2kit

from .connection import TrackerConn
from .deps import get_conn
from .enrichers import tracker_404_enricher
from .models import Project, Task
from .storage import TrackerStore


class ProjectsRouter(a2kit.Router):
    enricher = staticmethod(tracker_404_enricher)

    @a2kit.list_()
    async def list_projects(self, *, conn: TrackerConn = Depends(get_conn)) -> list[Project]:
        projects, _ = TrackerStore(conn).load_state()
        return projects

    @a2kit.read()
    async def get_project(self, *, conn: TrackerConn = Depends(get_conn), project_id: str) -> Project:
        projects, _ = TrackerStore(conn).load_state()
        for p in projects:
            if p.id == project_id:
                return p
        raise KeyError(project_id)

    @a2kit.write()
    async def create_project(self, *, conn: TrackerConn = Depends(get_conn), name: str) -> Project:
        store = TrackerStore(conn)
        projects, tasks = store.load_state()
        new = Project(id=str(uuid.uuid4())[:8], name=name)
        projects.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def archive_project(self, *, conn: TrackerConn = Depends(get_conn), project_id: str) -> Project:
        store = TrackerStore(conn)
        projects, tasks = store.load_state()
        for i, p in enumerate(projects):
            if p.id == project_id:
                projects[i] = p.model_copy(update={"archived": True})
                store.replace(projects, tasks)
                return projects[i]
        raise KeyError(project_id)


class TasksRouter(a2kit.Router):
    enricher = staticmethod(tracker_404_enricher)

    @a2kit.list_()
    async def list_tasks(
        self,
        *,
        conn: TrackerConn = Depends(get_conn),
        project_id: str | None = None,
    ) -> list[Task]:
        _, tasks = TrackerStore(conn).load_state()
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        return tasks

    @a2kit.read()
    async def get_task(self, *, conn: TrackerConn = Depends(get_conn), task_id: str) -> Task:
        _, tasks = TrackerStore(conn).load_state()
        for t in tasks:
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    @a2kit.write()
    async def create_task(
        self,
        *,
        conn: TrackerConn = Depends(get_conn),
        project_id: str,
        title: str,
    ) -> Task:
        store = TrackerStore(conn)
        projects, tasks = store.load_state()
        if not any(p.id == project_id for p in projects):
            raise KeyError(project_id)
        new = Task(id=str(uuid.uuid4())[:8], project_id=project_id, title=title)
        tasks.append(new)
        store.replace(projects, tasks)
        return new

    @a2kit.write()
    async def complete_task(self, *, conn: TrackerConn = Depends(get_conn), task_id: str) -> Task:
        store = TrackerStore(conn)
        projects, tasks = store.load_state()
        for i, t in enumerate(tasks):
            if t.id == task_id:
                tasks[i] = t.model_copy(update={"done": True})
                store.replace(projects, tasks)
                return tasks[i]
        raise KeyError(task_id)
