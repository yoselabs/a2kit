"""extract_facts.py emits a ``pyproject`` collection with upper-bound flags."""

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
    return tmp_path


def _write_pyproject(repo: Path, content: str) -> None:
    (repo / "pyproject.toml").write_text(content, encoding="utf-8")


def test_upper_bound_detection_matrix(repo_root: Path) -> None:
    _write_pyproject(
        repo_root,
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["fastapi>=0.115,<0.130", "httpx", "pydantic>=2", "click~=8.1"]\n',
    )
    facts = _extract_with_root(repo_root)
    deps = {d["name"]: d for d in facts["pyproject"]["dependencies"]}
    assert deps["fastapi"]["has_upper_bound"] is True
    assert deps["httpx"]["has_upper_bound"] is False
    assert deps["pydantic"]["has_upper_bound"] is False
    assert deps["click"]["has_upper_bound"] is True


def test_optional_dependencies_grouped(repo_root: Path) -> None:
    _write_pyproject(
        repo_root,
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n[project.optional-dependencies]\ntest = ["pytest"]\notel = ["opentelemetry-api>=1.20"]\n',
    )
    facts = _extract_with_root(repo_root)
    opt = facts["pyproject"]["optional_dependencies"]
    assert "test" in opt
    assert opt["test"][0]["name"] == "pytest"
    assert opt["test"][0]["has_upper_bound"] is False


def test_build_system_requires(repo_root: Path) -> None:
    _write_pyproject(
        repo_root,
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n[build-system]\nrequires = ["hatchling>=1,<2"]\nbuild-backend = "hatchling.build"\n',
    )
    facts = _extract_with_root(repo_root)
    bsr = facts["pyproject"]["build_system_requires"]
    assert len(bsr) == 1
    assert bsr[0]["name"] == "hatchling"
    assert bsr[0]["has_upper_bound"] is True


def test_pyproject_absent_yields_empty_collection(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    facts = _extract_with_root(tmp_path)
    assert facts["pyproject"] == {"dependencies": [], "optional_dependencies": {}, "build_system_requires": []}
