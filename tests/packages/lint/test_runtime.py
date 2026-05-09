"""Runtime-check tests using a duck-typed fake server."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from a2kit.packages.lint.runtime import (
    A2KR001,
    A2KR002,
    A2KR003,
    A2KR004,
    run_runtime_checks,
)


@dataclass
class _FakeTool:
    name: str


class _FakeManager:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list_tools(self) -> list[_FakeTool]:
        return [_FakeTool(n) for n in self._names]


class _FakeServer:
    def __init__(self, names: list[str]) -> None:
        self._tool_manager = _FakeManager(names)


def _write_snap(snap_dir: Path, name: str, payload: dict | str) -> Path:
    snap_dir.mkdir(parents=True, exist_ok=True)
    p = snap_dir / f"{name}.json"
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


def test_a2kr001_missing_snapshot(tmp_path: Path) -> None:
    server = _FakeServer(["alpha", "beta"])
    snap = tmp_path / "snaps"
    snap.mkdir()
    _write_snap(snap, "alpha", {"x": 1})
    findings = run_runtime_checks(server, config={"snapshot_dir": str(snap)})
    codes = {f.rule for f in findings}
    targets = {f.target for f in findings}
    assert A2KR001 in codes
    assert "beta" in targets


def test_a2kr002_per_tool_budget(tmp_path: Path) -> None:
    server = _FakeServer(["big"])
    snap = tmp_path / "snaps"
    _write_snap(snap, "big", "x" * 5000)
    findings = run_runtime_checks(
        server,
        config={"snapshot_dir": str(snap), "budgets": {"big": 100}},
    )
    assert any(f.rule == A2KR002 for f in findings)


def test_a2kr003_total_budget(tmp_path: Path) -> None:
    server = _FakeServer(["a", "b"])
    snap = tmp_path / "snaps"
    _write_snap(snap, "a", "x" * 1000)
    _write_snap(snap, "b", "x" * 1000)
    findings = run_runtime_checks(
        server,
        config={"snapshot_dir": str(snap), "total_budget": 500},
    )
    assert any(f.rule == A2KR003 for f in findings)


def test_a2kr004_similar_tool_names() -> None:
    server = _FakeServer(["fetch_user", "fetch_users"])
    findings = run_runtime_checks(server)
    assert any(f.rule == A2KR004 for f in findings)


def test_disabled_rule_skipped(tmp_path: Path) -> None:
    server = _FakeServer(["alpha"])
    snap = tmp_path / "snaps"
    snap.mkdir()
    findings = run_runtime_checks(server, config={"snapshot_dir": str(snap)}, disabled=[A2KR001])
    assert all(f.rule != A2KR001 for f in findings)


def test_no_snapshot_dir_means_no_a2kr001() -> None:
    server = _FakeServer(["alpha"])
    findings = run_runtime_checks(server)
    assert all(f.rule != A2KR001 for f in findings)
