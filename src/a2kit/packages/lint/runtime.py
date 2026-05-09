"""Runtime checks (A2KR001..A2KR004) for an importable FastMCP-style server.

These checks introspect a server *object*, not source. They run after the user
imports a target via ``a2kit lint runtime --import path:server``. We never
import fastmcp from this file — the server object is duck-typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


A2KR001 = "A2KR001"
A2KR002 = "A2KR002"
A2KR003 = "A2KR003"
A2KR004 = "A2KR004"

ALL_CHECKS = (A2KR001, A2KR002, A2KR003, A2KR004)


@dataclass(frozen=True)
class CheckMessage:
    """Single runtime check finding."""

    rule: str
    target: str
    message: str

    def format_concise(self) -> str:
        return f"{self.target}: {self.rule} {self.message}"


def _list_tool_names(server: Any) -> list[str]:
    try:
        tools = server._tool_manager.list_tools()  # noqa: SLF001
    except AttributeError:
        return []
    return [getattr(t, "name", "") for t in tools]


def check_snapshot_presence(server: Any, config: dict[str, Any]) -> Iterable[CheckMessage]:
    """A2KR001 — every tool must have a snapshot file."""
    snap_dir = config.get("snapshot_dir")
    if snap_dir is None:
        return
    snap = Path(snap_dir)
    for name in _list_tool_names(server):
        if not (snap / f"{name}.json").exists():
            yield CheckMessage(
                rule=A2KR001,
                target=name,
                message=f"missing snapshot at {snap / f'{name}.json'} (run with --update-schema-snapshots)",
            )


def check_per_tool_budget(server: Any, config: dict[str, Any]) -> Iterable[CheckMessage]:
    """A2KR002 — each snapshot file size <= declared budget."""
    snap_dir = config.get("snapshot_dir")
    budgets: dict[str, int] = config.get("budgets", {}) or {}
    if snap_dir is None or not budgets:
        return
    snap = Path(snap_dir)
    for name in _list_tool_names(server):
        budget = budgets.get(name)
        if budget is None:
            continue
        path = snap / f"{name}.json"
        if not path.exists():
            continue
        size = path.stat().st_size
        if size > budget:
            yield CheckMessage(
                rule=A2KR002,
                target=name,
                message=f"snapshot size {size}B exceeds declared budget {budget}B",
            )


def check_total_budget(server: Any, config: dict[str, Any]) -> Iterable[CheckMessage]:
    """A2KR003 — sum of snapshot file sizes <= total budget."""
    snap_dir = config.get("snapshot_dir")
    total = config.get("total_budget")
    if snap_dir is None or total is None:
        return
    snap = Path(snap_dir)
    if not snap.exists():
        return
    actual = sum(p.stat().st_size for p in snap.glob("*.json"))
    if actual > total:
        yield CheckMessage(
            rule=A2KR003,
            target=str(snap),
            message=f"total snapshot size {actual}B exceeds budget {total}B",
        )


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def check_similar_tool_names(server: Any, config: dict[str, Any]) -> Iterable[CheckMessage]:
    """A2KR004 — tool names with edit-distance < 2 confuse agents."""
    names = _list_tool_names(server)
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if (a, b) in seen or (b, a) in seen:
                continue
            if _edit_distance(a, b) < 2:
                seen.add((a, b))
                yield CheckMessage(
                    rule=A2KR004,
                    target=f"{a} / {b}",
                    message=f"tool names {a!r} and {b!r} are too similar",
                )


_CHECKS = (
    (A2KR001, check_snapshot_presence),
    (A2KR002, check_per_tool_budget),
    (A2KR003, check_total_budget),
    (A2KR004, check_similar_tool_names),
)


def run_runtime_checks(
    server: Any,
    *,
    store: Any | None = None,
    config: dict[str, Any] | None = None,
    disabled: Iterable[str] = (),
) -> list[CheckMessage]:
    """Run all runtime checks. Returns concatenated findings."""
    cfg = config or {}
    disabled_set = set(disabled)
    out: list[CheckMessage] = []
    for code, fn in _CHECKS:
        if code in disabled_set:
            continue
        out.extend(fn(server, cfg))
    return out


# v1.0 alias for the public surface.
run_runtime = run_runtime_checks


__all__ = [
    "A2KR001",
    "A2KR002",
    "A2KR003",
    "A2KR004",
    "ALL_CHECKS",
    "CheckMessage",
    "check_per_tool_budget",
    "check_similar_tool_names",
    "check_snapshot_presence",
    "check_total_budget",
    "run_runtime",
    "run_runtime_checks",
]
