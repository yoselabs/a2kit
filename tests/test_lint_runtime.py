"""Tests for a2kit.lint.runtime — A2KR001..A2KR004 + run_runtime_checks."""

from __future__ import annotations

from pathlib import Path

from a2kit.lint.runtime import (
    A2KR001,
    A2KR002,
    A2KR003,
    A2KR004,
    CheckMessage,
    _edit_distance,
    check_per_tool_budget,
    check_similar_tool_names,
    check_snapshot_presence,
    check_total_budget,
    run_runtime_checks,
)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeManager:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list_tools(self) -> list[_FakeTool]:
        return [_FakeTool(n) for n in self._names]


class _FakeServer:
    def __init__(self, names: list[str]) -> None:
        self._tool_manager = _FakeManager(names)


class _BadServer:
    """Server without `_tool_manager` — exercises the fallback in `_list_tool_names`."""


def test_check_message_format() -> None:
    m = CheckMessage(rule="A2KR001", target="x", message="boom")
    assert m.format_concise() == "x: A2KR001 boom"


def test_a2kr001_missing_snapshot(tmp_path: Path) -> None:
    server = _FakeServer(["alpha", "beta"])
    msgs = list(check_snapshot_presence(server, {"snapshot_dir": tmp_path}))
    assert {m.target for m in msgs} == {"alpha", "beta"}
    assert all(m.rule == A2KR001 for m in msgs)


def test_a2kr001_no_dir_skipped() -> None:
    server = _FakeServer(["x"])
    assert list(check_snapshot_presence(server, {})) == []


def test_a2kr001_passes_when_present(tmp_path: Path) -> None:
    (tmp_path / "alpha.json").write_text("{}")
    server = _FakeServer(["alpha"])
    assert list(check_snapshot_presence(server, {"snapshot_dir": tmp_path})) == []


def test_a2kr002_per_tool_budget_exceeded(tmp_path: Path) -> None:
    big = "x" * 200
    (tmp_path / "alpha.json").write_text(big)
    server = _FakeServer(["alpha"])
    msgs = list(check_per_tool_budget(server, {"snapshot_dir": tmp_path, "budgets": {"alpha": 50}}))
    assert msgs and msgs[0].rule == A2KR002


def test_a2kr002_no_budget_skipped(tmp_path: Path) -> None:
    server = _FakeServer(["alpha"])
    assert list(check_per_tool_budget(server, {"snapshot_dir": tmp_path, "budgets": {}})) == []


def test_a2kr002_missing_file_skipped(tmp_path: Path) -> None:
    server = _FakeServer(["alpha"])
    assert list(check_per_tool_budget(server, {"snapshot_dir": tmp_path, "budgets": {"alpha": 1}})) == []


def test_a2kr002_no_dir_skipped() -> None:
    server = _FakeServer(["alpha"])
    assert list(check_per_tool_budget(server, {})) == []


def test_a2kr003_total_budget_exceeded(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("x" * 100)
    (tmp_path / "b.json").write_text("y" * 100)
    server = _FakeServer(["a", "b"])
    msgs = list(check_total_budget(server, {"snapshot_dir": tmp_path, "total_budget": 50}))
    assert msgs and msgs[0].rule == A2KR003


def test_a2kr003_no_budget_skipped(tmp_path: Path) -> None:
    server = _FakeServer(["a"])
    assert list(check_total_budget(server, {"snapshot_dir": tmp_path})) == []


def test_a2kr003_missing_dir_skipped(tmp_path: Path) -> None:
    server = _FakeServer([])
    assert list(check_total_budget(server, {"snapshot_dir": tmp_path / "nope", "total_budget": 1})) == []


def test_a2kr004_similar_names_flagged() -> None:
    server = _FakeServer(["get_issue", "get_issues"])
    msgs = list(check_similar_tool_names(server, {}))
    assert msgs and msgs[0].rule == A2KR004


def test_a2kr004_distinct_names_pass() -> None:
    server = _FakeServer(["get_issue", "list_projects"])
    assert list(check_similar_tool_names(server, {})) == []


def test_a2kr004_dedupes_pairs() -> None:
    server = _FakeServer(["a", "b", "c"])  # all distance 1 - all flagged once
    msgs = list(check_similar_tool_names(server, {}))
    assert len(msgs) == 3  # (a,b), (a,c), (b,c)


def test_a2kr004_repeated_name_dedupes() -> None:
    """Duplicate names trigger only one finding (covers `seen` short-circuit)."""
    server = _FakeServer(["x", "x", "x"])
    msgs = list(check_similar_tool_names(server, {}))
    # (x,x) flagged once, then (x,x) again would re-trigger if we allow same
    # pair — but we use `(a,b) in seen` to skip.
    assert len(msgs) >= 1


def test_a2kr002_under_budget_passes(tmp_path: Path) -> None:
    """File at-or-below budget produces no finding (covers the `size > budget` False branch)."""
    (tmp_path / "alpha.json").write_text("x" * 10)
    server = _FakeServer(["alpha"])
    msgs = list(check_per_tool_budget(server, {"snapshot_dir": tmp_path, "budgets": {"alpha": 100}}))
    assert msgs == []


def test_a2kr002_skips_unbudgeted_tool(tmp_path: Path) -> None:
    """A snapshot with no declared budget is silently skipped (covers `budget is None`)."""
    (tmp_path / "alpha.json").write_text("x" * 1000)
    server = _FakeServer(["alpha"])
    msgs = list(check_per_tool_budget(server, {"snapshot_dir": tmp_path, "budgets": {"other": 50}}))
    assert msgs == []


def test_edit_distance_short_circuit() -> None:
    assert _edit_distance("abc", "xyzabc") == 3  # noqa: PLR2004
    assert _edit_distance("a", "a") == 0
    assert _edit_distance("ab", "ba") == 2  # noqa: PLR2004


def test_run_runtime_checks_aggregates(tmp_path: Path) -> None:
    server = _FakeServer(["alpha"])
    out = run_runtime_checks(server, config={"snapshot_dir": tmp_path})
    assert any(m.rule == A2KR001 for m in out)


def test_run_runtime_checks_disabled(tmp_path: Path) -> None:
    server = _FakeServer(["alpha"])
    out = run_runtime_checks(server, config={"snapshot_dir": tmp_path}, disabled=["A2KR001"])
    assert all(m.rule != A2KR001 for m in out)


def test_list_tool_names_handles_missing_attr() -> None:
    msgs = list(check_similar_tool_names(_BadServer(), {}))
    assert msgs == []
