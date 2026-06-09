"""Capability tests for ``policies/github_actions.rego``.

Three rules: RG005, RG006, RG007.
Each test runs the policy bundle against synthetic facts with a fully
isolated allowlist so production data.json is invisible.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .conftest import POLICIES_DIR, REGO_FILES


def _opa_eval_gha(facts: dict, allowlist: dict | None = None) -> list[dict]:
    """Run the rego bundle (existing rules + github_actions.rego) with an isolated allowlist."""
    rego_files = [*REGO_FILES, "github_actions.rego"]
    effective = (
        allowlist
        if allowlist is not None
        else {
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [],
            "github_actions_vendor_unpinned": [],
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


def _base_facts() -> dict[str, Any]:
    return {
        "functions": [],
        "modules": [],
        "suppressions": [],
        "workflows": [],
        "pyproject": {"dependencies": [], "optional_dependencies": {}, "build_system_requires": []},
    }


_DEFAULT_PERMS: dict[str, str] = {"contents": "read"}


def _wf(*, file: str = ".github/workflows/x.yml", permissions: Any = _DEFAULT_PERMS, jobs: list | None = None) -> dict:
    return {
        "file": file,
        "name": "X",
        "permissions": permissions,
        "on": ["push"],
        "jobs": jobs or [],
    }


def _step(*, uses: str | None, vendor: str | None = None, has_pinned_sha: bool = False, ref: str | None = None) -> dict:
    if uses is not None and vendor is None:
        vendor = uses.split("/")[0]
    if uses is not None and ref is None:
        ref = uses.split("@", 1)[1] if "@" in uses else None
    return {"uses": uses, "uses_ref": ref, "has_pinned_sha": has_pinned_sha, "vendor": vendor, "with_keys": []}


# ---------------------------------------------------------------------------- #
# RG005
# ---------------------------------------------------------------------------- #


def test_unpinned_vendor_action_fires() -> None:
    facts = _base_facts()
    facts["workflows"] = [_wf(jobs=[{"name": "j", "permissions": None, "steps": [_step(uses="tj-actions/changed-files@v1")]}])]
    findings = _opa_eval_gha(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [{"vendor": "tj-actions", "reason": "test allows vendor; pin-sha is the issue"}],
            "github_actions_vendor_unpinned": [],
        },
    )
    rules = {f["rule"] for f in findings}
    assert "RG005" in rules
    pin_msgs = [f for f in findings if f["rule"] == "RG005"]
    assert any("tj-actions/changed-files" in f["message"] for f in pin_msgs)


def test_pinned_sha_passes() -> None:
    facts = _base_facts()
    sha = "b4ffde65f46336ab88eb53be808477a3936bae11"
    facts["workflows"] = [
        _wf(jobs=[{"name": "j", "permissions": None, "steps": [_step(uses=f"actions/checkout@{sha}", has_pinned_sha=True)]}])
    ]
    findings = _opa_eval_gha(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [{"vendor": "actions", "reason": "test"}],
            "github_actions_vendor_unpinned": [],
        },
    )
    pin_msgs = [f for f in findings if f["rule"] == "RG005"]
    assert pin_msgs == []


def test_allowlisted_unpinned_vendor_exempt() -> None:
    facts = _base_facts()
    facts["workflows"] = [_wf(jobs=[{"name": "j", "permissions": None, "steps": [_step(uses="actions/setup-python@v5")]}])]
    findings = _opa_eval_gha(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [{"vendor": "actions", "reason": "first-party"}],
            "github_actions_vendor_unpinned": [{"vendor": "actions", "reason": "first-party, mutation risk accepted"}],
        },
    )
    pin_msgs = [f for f in findings if f["rule"] == "RG005"]
    assert pin_msgs == []


# ---------------------------------------------------------------------------- #
# RG006
# ---------------------------------------------------------------------------- #


def test_missing_top_level_permissions_fires() -> None:
    facts = _base_facts()
    facts["workflows"] = [_wf(permissions=None, jobs=[])]
    findings = _opa_eval_gha(facts)
    perm_msgs = [f for f in findings if f["rule"] == "RG006"]
    assert len(perm_msgs) == 1


def test_top_level_permissions_present_passes() -> None:
    facts = _base_facts()
    facts["workflows"] = [_wf(permissions={"contents": "read"}, jobs=[])]
    findings = _opa_eval_gha(facts)
    perm_msgs = [f for f in findings if f["rule"] == "RG006"]
    assert perm_msgs == []


# ---------------------------------------------------------------------------- #
# RG007
# ---------------------------------------------------------------------------- #


def test_unknown_vendor_fires() -> None:
    facts = _base_facts()
    facts["workflows"] = [
        _wf(jobs=[{"name": "j", "permissions": None, "steps": [_step(uses="someone-untrusted/spooky@sha", has_pinned_sha=True)]}])
    ]
    findings = _opa_eval_gha(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [{"vendor": "actions", "reason": "first-party"}],
            "github_actions_vendor_unpinned": [],
        },
    )
    vendor_msgs = [f for f in findings if f["rule"] == "RG007"]
    assert len(vendor_msgs) == 1
    assert "someone-untrusted" in vendor_msgs[0]["message"]


def test_allowlisted_vendor_passes() -> None:
    facts = _base_facts()
    sha = "b4ffde65f46336ab88eb53be808477a3936bae11"
    facts["workflows"] = [
        _wf(jobs=[{"name": "j", "permissions": None, "steps": [_step(uses=f"astral-sh/setup-uv@{sha}", has_pinned_sha=True)]}])
    ]
    findings = _opa_eval_gha(
        facts,
        allowlist={
            "body_dup": [],
            "name_collision": [],
            "github_actions_vendor": [{"vendor": "astral-sh", "reason": "uv vendor"}],
            "github_actions_vendor_unpinned": [],
        },
    )
    vendor_msgs = [f for f in findings if f["rule"] == "RG007"]
    assert vendor_msgs == []
