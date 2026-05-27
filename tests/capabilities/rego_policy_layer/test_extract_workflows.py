"""extract_facts.py emits a ``workflows`` collection from ``.github/workflows/*.yml``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import EXTRACT_SCRIPT


def _extract_with_root(repo_root: Path) -> dict:
    cmd = [sys.executable, str(EXTRACT_SCRIPT), "--repo-root", str(repo_root), str(repo_root / "src")]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"extract failed: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    return tmp_path


def _write_workflow(repo: Path, name: str, content: str) -> None:
    (repo / ".github" / "workflows" / name).write_text(content, encoding="utf-8")


def test_workflows_collection_present(repo_root: Path) -> None:
    _write_workflow(
        repo_root,
        "ci.yml",
        "name: CI\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n",
    )
    facts = _extract_with_root(repo_root)
    assert "workflows" in facts
    assert len(facts["workflows"]) == 1
    wf = facts["workflows"][0]
    assert wf["name"] == "CI"
    assert wf["file"].endswith("ci.yml")


def test_workflow_step_pin_detection_unpinned(repo_root: Path) -> None:
    _write_workflow(
        repo_root,
        "x.yml",
        "name: X\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n",
    )
    facts = _extract_with_root(repo_root)
    step = facts["workflows"][0]["jobs"][0]["steps"][0]
    assert step["uses_ref"] == "v4"
    assert step["has_pinned_sha"] is False
    assert step["vendor"] == "actions"


def test_workflow_step_pin_detection_pinned_sha(repo_root: Path) -> None:
    sha = "b4ffde65f46336ab88eb53be808477a3936bae11"
    _write_workflow(
        repo_root,
        "x.yml",
        f"name: X\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@{sha}\n",
    )
    facts = _extract_with_root(repo_root)
    step = facts["workflows"][0]["jobs"][0]["steps"][0]
    assert step["uses_ref"] == sha
    assert step["has_pinned_sha"] is True


def test_workflow_top_level_permissions_captured(repo_root: Path) -> None:
    _write_workflow(
        repo_root,
        "x.yml",
        "name: X\non: [push]\npermissions:\n  contents: read\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    facts = _extract_with_root(repo_root)
    wf = facts["workflows"][0]
    assert wf["permissions"] == {"contents": "read"}


def test_workflow_missing_permissions_is_null(repo_root: Path) -> None:
    _write_workflow(
        repo_root,
        "x.yml",
        "name: X\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    facts = _extract_with_root(repo_root)
    wf = facts["workflows"][0]
    assert wf["permissions"] is None


def test_workflow_step_run_only_no_uses(repo_root: Path) -> None:
    _write_workflow(
        repo_root,
        "x.yml",
        "name: X\non: [push]\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - name: hello\n        run: echo hi\n",
    )
    facts = _extract_with_root(repo_root)
    step = facts["workflows"][0]["jobs"][0]["steps"][0]
    assert step["uses"] is None
    assert step["has_pinned_sha"] is False
    assert step["vendor"] is None


def test_workflows_absent_yields_empty_collection(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    facts = _extract_with_root(tmp_path)
    assert facts["workflows"] == []
