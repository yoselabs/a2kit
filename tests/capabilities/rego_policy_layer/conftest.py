"""Shared helpers for rego-policy-layer capability tests.

Each test creates a tempdir with synthetic .py files (fixture-only —
the real repo's audit hits are deferred to Bundle A via the allowlist
in policies/data.json), runs the extract → opa pipeline, and asserts
findings shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXTRACT_SCRIPT = REPO_ROOT / "scripts" / "extract_facts.py"
POLICIES_DIR = REPO_ROOT / "policies"


@pytest.fixture()
def tmpsrc(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    return src


def write_py(root: Path, relpath: str, source: str) -> Path:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def extract(paths: list[Path]) -> dict:
    cmd = [sys.executable, str(EXTRACT_SCRIPT), *(str(p) for p in paths)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"extract failed: {proc.stderr}"
    return json.loads(proc.stdout)


def extract_returncode(paths: list[Path]) -> tuple[int, str]:
    """For tests that expect extract to fail (e.g. REGO-* noqa missing reason)."""
    cmd = [sys.executable, str(EXTRACT_SCRIPT), *(str(p) for p in paths)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stderr


REGO_FILES = ("_helpers.rego", "body_dup.rego", "name_collision.rego")


def opa_eval(facts: dict, *, allowlist: dict | None = None) -> list[dict]:
    """Run the policies against synthetic facts with an isolated allowlist.

    Loads .rego files explicitly (not the bundle), so the test allowlist
    fully replaces the production policies/data.json. When `allowlist`
    is None, uses an empty allowlist — production data.json is NEVER
    visible to the test (test isolation).
    """
    with _tmp_input(facts) as facts_path:
        cmd = ["opa", "eval"]
        for rego in REGO_FILES:
            cmd.extend(["--data", str(POLICIES_DIR / rego)])
        effective = allowlist if allowlist is not None else {"body_dup": [], "name_collision": []}
        with _tmp_data({"a2kit": {"allowlist": effective}}) as data_path:
            cmd.extend(["--data", str(data_path)])
            cmd.extend(["--input", str(facts_path)])
            cmd.extend(["--format", "json", "data.a2kit.deny"])
            return _run_opa(cmd)


def _run_opa(cmd: list[str]) -> list[dict[str, Any]]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"opa eval failed: {proc.stderr}"
    payload = json.loads(proc.stdout)
    results = payload.get("result", [])
    if not results:
        return []
    expressions = results[0].get("expressions", [])
    if not expressions:
        return []
    value = expressions[0].get("value", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


class _tmp_input:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.path: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        fd = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(self.data, fd)
        fd.flush()
        fd.close()
        self.path = Path(fd.name)
        return self.path

    def __exit__(self, *_exc: object) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)


_tmp_data = _tmp_input  # alias for readability at call sites
