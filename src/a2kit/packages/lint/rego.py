"""``a2kit lint rego`` — invoke OPA-based architectural policies.

Pipeline::

    scripts/extract_facts.py  →  facts.json
    opa eval --bundle policies/ --input facts.json 'data.a2kit.deny'
    → LintMessage[]

Findings adopt the same ``LintMessage`` shape as ``a2kit lint static`` so
the CLI output is uniform. Exit code 1 on any finding, mirroring static
lint. See ``docs/dev/rego-toolchain.md`` for the toolchain rationale.

This module is a thin wrapper. The policy logic lives in
``policies/*.rego`` (Open Policy Agent); the fact-extraction lives in
``scripts/extract_facts.py``. The wrapper imports ONLY stdlib + click +
``a2kit.packages.lint.static`` (for the ``LintMessage`` dataclass) — no
fastmcp, no a2kit runtime concepts. Mirrors ``packages/lint/cli.py``'s
import discipline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import click

from a2kit.packages.lint.static import LintMessage

EXTRACT_SCRIPT = Path("scripts/extract_facts.py")
POLICIES_DIR = Path("policies")
OPA_QUERY = "data.a2kit.deny"


class RegoWrapperError(Exception):
    """Surfaceable error from the rego wrapper (missing toolchain, etc.)."""


def _check_environment() -> None:
    if shutil.which("opa") is None:
        raise RegoWrapperError("opa not on PATH. Install with `brew install opa` (macOS) or see docs/dev/rego-toolchain.md.")
    if not EXTRACT_SCRIPT.is_file():
        raise RegoWrapperError(f"{EXTRACT_SCRIPT} not found. Run from the repo root.")
    if not POLICIES_DIR.is_dir():
        raise RegoWrapperError(f"{POLICIES_DIR}/ not found. Run from the repo root.")


def _run_extract(paths: tuple[str, ...], out_path: Path) -> None:
    cmd = [sys.executable, str(EXTRACT_SCRIPT), *paths, "-o", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 -- args composed from sys.executable + repo-local paths, not user input
    if proc.returncode != 0:
        raise RegoWrapperError(f"extract_facts.py failed (exit {proc.returncode}):\n{proc.stderr}")


def _run_opa(facts_path: Path) -> list[dict[str, Any]]:
    cmd = [
        "opa",
        "eval",
        "--bundle",
        str(POLICIES_DIR),
        "--input",
        str(facts_path),
        "--format",
        "json",
        OPA_QUERY,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 -- args are repo-local paths + literal opa query, not user input
    if proc.returncode != 0:
        raise RegoWrapperError(f"opa eval failed (exit {proc.returncode}):\n{proc.stderr}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RegoWrapperError(f"opa eval emitted unparseable JSON: {e}\n--- stdout ---\n{proc.stdout}") from e
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


def _to_lint_message(finding: dict) -> LintMessage:
    return LintMessage(
        rule=str(finding.get("rule", "REGO-UNKNOWN")),
        filename=str(finding.get("file", "?")),
        line=int(finding.get("line", 0) or 0),
        col=int(finding.get("col", 0) or 0),
        message=str(finding.get("message", "")),
    )


def run_rego_policies(paths: tuple[str, ...]) -> list[LintMessage]:
    """Run the OPA policy bundle against extracted facts. Returns findings.

    Raises ``RegoWrapperError`` for toolchain / pipeline failures (missing
    opa, missing scripts, malformed output). Policy `deny` findings are
    returned as `LintMessage` list; an empty list means clean.
    """
    _check_environment()
    if not paths:
        paths = ("src/",)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        facts_path = Path(tmp.name)
    try:
        _run_extract(paths, facts_path)
        findings = _run_opa(facts_path)
    finally:
        facts_path.unlink(missing_ok=True)
    return sorted(
        (_to_lint_message(f) for f in findings),
        key=lambda m: (m.filename, m.line, m.rule),
    )


@click.command("rego", help="Run OPA-based architectural policies (REGO-* rules).")
@click.argument("paths", nargs=-1)
def rego_cmd(paths: tuple[str, ...]) -> None:
    try:
        findings = run_rego_policies(paths)
    except RegoWrapperError as e:
        click.echo(f"a2kit lint rego: {e}", err=True)
        sys.exit(2)
    for f in findings:
        click.echo(f.format_concise())
    if findings:
        sys.exit(1)


__all__ = ["RegoWrapperError", "rego_cmd", "run_rego_policies"]
