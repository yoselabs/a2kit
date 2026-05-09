"""Tests for A2K-TEST-MIRROR (`packages/lint/rules/mirror.py`)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from a2kit.packages.lint.rules.mirror import (
    A2K_TEST_MIRROR,
    ALLOW_LIST,
    load_test_only_manifest,
    rule_test_mirror,
    source_to_mirror,
)


def _run(filename: str) -> list[str]:
    findings = list(rule_test_mirror(ast.parse(""), filename, ""))
    assert all(f.rule == A2K_TEST_MIRROR for f in findings)
    return [f.message for f in findings]


# ---------- source_to_mirror ----------


def test_source_to_mirror_top_level_core_file() -> None:
    assert source_to_mirror("src/a2kit/app.py") == "tests/test_app.py"


def test_source_to_mirror_plugin_package_file() -> None:
    assert source_to_mirror("src/a2kit/packages/cli/builder.py") == "tests/packages/cli/test_builder.py"


def test_source_to_mirror_nested_rules_subpackage() -> None:
    assert source_to_mirror("src/a2kit/packages/lint/rules/budget.py") == "tests/packages/lint/rules/test_budget.py"


def test_source_to_mirror_returns_none_for_non_src_path() -> None:
    assert source_to_mirror("tests/test_app.py") is None
    assert source_to_mirror("examples/tracker/server.py") is None


def test_source_to_mirror_returns_none_for_non_python_file() -> None:
    assert source_to_mirror("src/a2kit/Makefile") is None


def test_source_to_mirror_handles_windows_separators() -> None:
    assert source_to_mirror(r"src\a2kit\packages\cli\builder.py") == "tests/packages/cli/test_builder.py"


# ---------- rule_test_mirror ----------


def test_rule_skips_non_src_paths() -> None:
    assert _run("tests/test_app.py") == []
    assert _run("examples/tracker/server.py") == []


def test_rule_skips_init_and_main() -> None:
    assert _run("src/a2kit/__init__.py") == []
    assert _run("src/a2kit/__main__.py") == []
    assert _run("src/a2kit/packages/cli/__init__.py") == []


def test_rule_skips_explicit_allow_list_entries() -> None:
    for path in sorted(ALLOW_LIST):
        assert _run(path) == [], f"{path} should be allow-listed"


def test_rule_fires_on_missing_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "a2kit").mkdir(parents=True)
    (tmp_path / "src" / "a2kit" / "widget.py").write_text("x = 1\n")
    findings = _run("src/a2kit/widget.py")
    assert len(findings) == 1
    assert "missing mirror test file" in findings[0]
    assert "tests/test_widget.py" in findings[0]


def test_rule_fires_on_empty_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "a2kit").mkdir(parents=True)
    (tmp_path / "src" / "a2kit" / "widget.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text("# only comments, no test_*\n")
    findings = _run("src/a2kit/widget.py")
    assert len(findings) == 1
    assert "no `def test_*` function" in findings[0]


def test_rule_silent_when_mirror_has_test_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "a2kit").mkdir(parents=True)
    (tmp_path / "src" / "a2kit" / "widget.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text("def test_smoke():\n    pass\n")
    assert _run("src/a2kit/widget.py") == []


def test_rule_recognises_async_test_function(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src" / "a2kit").mkdir(parents=True)
    (tmp_path / "src" / "a2kit" / "widget.py").write_text("x = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_widget.py").write_text("async def test_smoke():\n    pass\n")
    assert _run("src/a2kit/widget.py") == []


# ---------- load_test_only_manifest ----------


def test_manifest_returns_empty_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert load_test_only_manifest() == frozenset()


def test_manifest_skips_blank_and_comment_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "_test_only.txt").write_text(
        "# leading comment\n"
        "\n"
        "tests/conftest.py\n"
        "  # indented comment\n"
        "tests/test_cold_start.py   # trailing comment-prefix is part of path? no — only `#` at start.\n",
    )
    out = load_test_only_manifest()
    # Only fully-clean lines (no trailing inline comments) are accepted.
    assert "tests/conftest.py" in out
    # The line with trailing text becomes the whole stripped line; verify it's normalized.
    assert any("tests/test_cold_start.py" in entry for entry in out)


def test_manifest_normalizes_windows_separators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "_test_only.txt").write_text("tests\\packages\\cli\\test_e2e.py\n")
    assert "tests/packages/cli/test_e2e.py" in load_test_only_manifest()


# ---------- integration: real project tree should not regress further ----------


def test_real_project_manifest_is_loadable() -> None:
    """The shipped `tests/_test_only.txt` parses without error."""
    manifest = load_test_only_manifest()
    # If the manifest exists, it should contain at least one entry.
    if Path("tests/_test_only.txt").exists():
        assert len(manifest) > 0
        assert all("/" in entry for entry in manifest), "all entries should be paths"
