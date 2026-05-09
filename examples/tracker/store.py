from __future__ import annotations

from pathlib import Path

from .connection import TrackerConn
from .models import Project, Task


class TrackerStore:
    """Project + task persistence backed by one connection's JSONL file."""

    def __init__(self, conn: TrackerConn) -> None:
        self.conn = conn
        self.db_path = Path(conn.db_path)

    def load_state(self) -> tuple[list[Project], list[Task]]:
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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = [p.model_dump_json() for p in projects]
        lines.extend(t.model_dump_json() for t in tasks)
        self.db_path.write_text("\n".join(lines) + ("\n" if lines else ""))
