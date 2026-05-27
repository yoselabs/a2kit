"""1.6 — `a2kit lint rego` subcommand exit codes and finding rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_dirty_tree(tmp_path: Path) -> Path:
    """A synthetic src tree containing a known body-dup pair."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text(
        "def _helper():\n    out = []\n    for x in range(3):\n        out.append(x * 2)\n    return out\n",
        encoding="utf-8",
    )
    (src / "b.py").write_text(
        "def _helper():\n    res = []\n    for y in range(3):\n        res.append(y * 2)\n    return res\n",
        encoding="utf-8",
    )
    return src


def _make_clean_tree(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    return src


def _run_lint_rego(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    cmd = ["uv", "run", "a2kit", "lint", "rego", *(str(p) for p in paths)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=REPO_ROOT)


def test_dirty_tree_exits_nonzero_with_structured_findings(tmp_path):
    dirty = _make_dirty_tree(tmp_path)
    proc = _run_lint_rego([dirty])
    assert proc.returncode == 1, f"expected exit 1, got {proc.returncode}; stderr={proc.stderr}"
    assert "REGO-BODY-DUP" in proc.stdout or "REGO-NAME-COLLISION" in proc.stdout
    # LintMessage shape: file:line:col: RULE message
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert all(":" in line for line in lines)


def test_clean_tree_exits_zero(tmp_path):
    clean = _make_clean_tree(tmp_path)
    proc = _run_lint_rego([clean])
    assert proc.returncode == 0, f"expected exit 0, got {proc.returncode}; stdout={proc.stdout} stderr={proc.stderr}"
    assert proc.stdout.strip() == ""
