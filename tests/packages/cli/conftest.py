"""Shared fixtures for cli package tests — small App with one Router."""

from __future__ import annotations

import pytest

import a2kit


class TasksRouter(a2kit.Router):
    name = "tasks"

    @a2kit.read()
    def get_task(self, *, task_id: int) -> dict:
        """Return a single task by id."""
        return {"id": task_id, "title": f"task-{task_id}"}

    @a2kit.list_()
    def list_tasks(self, *, limit: int = 10) -> list[dict]:
        """List tasks."""
        return [{"id": i, "title": f"task-{i}"} for i in range(limit)]

    @a2kit.write()
    def create_task(self, *, title: str, done: bool = False) -> dict:
        """Create a task."""
        return {"title": title, "done": done}


@pytest.fixture
def tasks_router() -> TasksRouter:
    return TasksRouter()


@pytest.fixture
def app(tasks_router: TasksRouter) -> a2kit.App:
    a = a2kit.App("tracker")
    a.use(tasks_router)
    return a
