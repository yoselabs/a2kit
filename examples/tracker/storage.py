"""`TrackerStore` — a class wrapping the JSONL persistence for one connection.

Constructed from a `TrackerConn`, it exposes the operations tools care
about: `load_state()` returns the parsed projects + tasks, `replace()`
writes back. Tools build a store per call:

    store = TrackerStore(conn)
    projects, tasks = store.load_state()

The class is the boundary worth swapping: a real backend would replace
`TrackerStore` with a database client; nothing else in the example moves.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .models import Project, Task

if TYPE_CHECKING:
    from .connection import TrackerConn


class TrackerStore:
    """Project + task persistence backed by one connection's JSONL file.

    The file is a flat append-only log of projects and tasks, distinguished
    by Pydantic's `project_id` field (tasks have it; projects don't). A
    real app would split into two files or a real database; the example
    keeps it in one to stay readable.
    """

    def __init__(self, conn: TrackerConn) -> None:
        self.conn = conn
        self.db_path = Path(conn.db_path)

    def load_state(self) -> tuple[list[Project], list[Task]]:
        """Read the JSONL file; return (projects, tasks)."""
        if not self.db_path.exists():
            return [], []
        projects: list[Project] = []
        tasks: list[Task] = []
        for line in self.db_path.read_text().splitlines():
            if not line.strip():
                continue
            if '"project_id"' in line:
                tasks.append(Task.model_validate_json(line))
            else:
                projects.append(Project.model_validate_json(line))
        return projects, tasks

    def replace(self, projects: list[Project], tasks: list[Task]) -> None:
        """Replace the file with the given state. Caller computes the new state."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = [p.model_dump_json() for p in projects]
        lines.extend(t.model_dump_json() for t in tasks)
        self.db_path.write_text("\n".join(lines) + ("\n" if lines else ""))
