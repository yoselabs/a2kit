"""Tests for a2kit.lint.cli — argparse + integration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from a2kit.lint import cli as lint_cli


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeManager:
    def list_tools(self) -> list[_FakeTool]:
        return [_FakeTool("alpha"), _FakeTool("alphax")]


class _FakeServer:
    _tool_manager = _FakeManager()


def test_cli_lint_no_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "ok.py"
    p.write_text(
        """
import a2kit
@a2kit.tool()
def f() -> dict:
    return {}
"""
    )
    rc = lint_cli.main(["lint", str(p)])
    assert rc == 0


def test_cli_lint_with_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = tmp_path / "bad.py"
    p.write_text(
        """
import a2kit
@a2kit.tool()
def f() -> str:
    return ""
"""
    )
    rc = lint_cli.main(["lint", str(p)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "A2K002" in out


def test_cli_lint_disabled_clears_findings(tmp_path: Path) -> None:
    p = tmp_path / "bad.py"
    p.write_text(
        """
import a2kit
@a2kit.tool()
def f() -> str:
    return ""
"""
    )
    rc = lint_cli.main(["lint", str(p), "--disabled", "A2K002"])
    assert rc == 0


def test_cli_lint_directory(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ok.py").write_text("x = 1\n")
    rc = lint_cli.main(["lint", str(sub)])
    assert rc == 0


def test_cli_lint_skips_non_existent(tmp_path: Path) -> None:
    rc = lint_cli.main(["lint", str(tmp_path / "nope")])
    assert rc == 0


def test_cli_check_runs_against_imported_server(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = type(sys)("fake_a2kit_test_mod")
    fake_module.server = _FakeServer()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_a2kit_test_mod", fake_module)
    rc = lint_cli.main(["check", "--import", "fake_a2kit_test_mod:server"])
    # alpha vs alphax = edit distance 1 → flag → rc=1
    assert rc == 1


def test_cli_check_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_module = type(sys)("fake_a2kit_test_mod2")
    fake_module.server = _FakeServer()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_a2kit_test_mod2", fake_module)
    rc = lint_cli.main(["check", "--import", "fake_a2kit_test_mod2:server", "--disabled", "A2KR004"])
    assert rc == 0


def test_cli_check_with_snapshot_and_budget(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Empty:
        _tool_manager = _FakeManager()

    fake_module = type(sys)("fake_a2kit_test_mod3")
    fake_module.server = _Empty()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_a2kit_test_mod3", fake_module)
    rc = lint_cli.main(
        [
            "check",
            "--import",
            "fake_a2kit_test_mod3:server",
            "--snapshot-dir",
            str(tmp_path),
            "--total-budget",
            "1",
            "--disabled",
            "A2KR004",
        ]
    )
    # snapshots missing → A2KR001 fires
    assert rc == 1


def test_cli_import_target_bad_format() -> None:
    with pytest.raises(ValueError, match="module:attr"):
        lint_cli._import_target("just_a_name")


def test_cli_main_module_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover the `if __name__ == '__main__'` import path indirectly."""
    rc = lint_cli.main(["lint", "/tmp/this-path-is-empty"])  # noqa: S108
    assert rc == 0
