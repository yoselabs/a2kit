"""Capability tests for ``policies/pyproject.rego``."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .conftest import POLICIES_DIR, REGO_FILES


def _opa_eval_py(facts: dict, allowlist: dict | None = None) -> list[dict]:
    rego_files = [*REGO_FILES, "pyproject.rego"]
    effective = (
        allowlist
        if allowlist is not None
        else {
            "body_dup": [],
            "name_collision": [],
            "pyproject_upper_bound": [],
        }
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as input_f:
        json.dump(facts, input_f)
        input_f.flush()
        input_path = Path(input_f.name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as data_f:
        json.dump({"a2kit": {"allowlist": effective}}, data_f)
        data_f.flush()
        data_path = Path(data_f.name)
    try:
        cmd = ["opa", "eval"]
        for rego in rego_files:
            cmd.extend(["--data", str(POLICIES_DIR / rego)])
        cmd.extend(["--data", str(data_path)])
        cmd.extend(["--input", str(input_path)])
        cmd.extend(["--format", "json", "data.a2kit.deny"])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, f"opa eval failed: {proc.stderr}"
        payload = json.loads(proc.stdout)
        results = payload.get("result", [])
        if not results:
            return []
        return [item for item in results[0].get("expressions", [{}])[0].get("value", []) if isinstance(item, dict)]
    finally:
        input_path.unlink(missing_ok=True)
        data_path.unlink(missing_ok=True)


def _facts(deps: list[dict[str, Any]], optional: dict | None = None) -> dict:
    return {
        "functions": [],
        "modules": [],
        "suppressions": [],
        "workflows": [],
        "pyproject": {
            "dependencies": deps,
            "optional_dependencies": optional or {},
            "build_system_requires": [],
        },
    }


def test_bare_dep_fires() -> None:
    facts = _facts([{"name": "httpx", "spec": "httpx", "has_upper_bound": False}])
    findings = _opa_eval_py(facts)
    msgs = [f for f in findings if f["rule"] == "REGO-PYPROJECT-UPPER-BOUND"]
    assert len(msgs) == 1
    assert "httpx" in msgs[0]["message"]


def test_dep_with_upper_bound_passes() -> None:
    facts = _facts([{"name": "fastapi", "spec": "fastapi>=0.115,<0.130", "has_upper_bound": True}])
    findings = _opa_eval_py(facts)
    msgs = [f for f in findings if f["rule"] == "REGO-PYPROJECT-UPPER-BOUND"]
    assert msgs == []


def test_optional_dep_without_upper_bound_passes() -> None:
    facts = _facts(
        [{"name": "fastapi", "spec": "fastapi>=0.115,<0.130", "has_upper_bound": True}],
        optional={"test": [{"name": "pytest", "spec": "pytest", "has_upper_bound": False}]},
    )
    findings = _opa_eval_py(facts)
    msgs = [f for f in findings if f["rule"] == "REGO-PYPROJECT-UPPER-BOUND"]
    assert msgs == []


def test_allowlisted_runtime_dep_exempt() -> None:
    facts = _facts([{"name": "fastmcp", "spec": "fastmcp", "has_upper_bound": False}])
    findings = _opa_eval_py(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "pyproject_upper_bound": [{"name": "fastmcp", "reason": "pre-1.0; pin via uv.lock"}],
        },
    )
    msgs = [f for f in findings if f["rule"] == "REGO-PYPROJECT-UPPER-BOUND"]
    assert msgs == []
