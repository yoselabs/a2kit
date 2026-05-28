"""``a2kit lint rego`` — invoke OPA-based architectural policies.

Pipeline::

    extract_facts.py  →  facts.json
    opa eval --bundle <packaged-policies> --data <project-data.json> \\
        --input facts.json 'data.a2kit.deny'
    → LintMessage[]

The policy bundle (``.rego`` files + ``extract_facts.py``) ships INSIDE
the package at ``a2kit/packages/lint/_bundle/``. Consumers don't vendor
those files — they only ship a per-project ``policies/data.json``
(allowlist with reasons) at their repo root. ``--policies-dir`` and
``--extract-script`` flags override the bundle if a consumer needs to
fork the rules entirely.

Findings adopt the same ``LintMessage`` shape as ``a2kit lint static`` so
the CLI output is uniform. Exit code 1 on any finding, mirroring static
lint. See ``docs/dev/rego-toolchain.md`` for the toolchain rationale.

This module is a thin wrapper. The policy logic lives in
``_bundle/policies/*.rego`` (Open Policy Agent); fact-extraction lives
in ``_bundle/extract_facts.py``. The wrapper imports ONLY stdlib + click
+ ``a2kit.packages.lint.static`` (for the ``LintMessage`` dataclass) —
no fastmcp, no a2kit runtime concepts. Mirrors
``packages/lint/cli.py``'s import discipline.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator  # noqa: TC003 -- used in runtime annotation (contextmanager return)
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import click

from a2kit.packages.lint.static import LintMessage

_BUNDLE_DIR = Path(__file__).parent / "_bundle"
BUNDLED_POLICIES_DIR = _BUNDLE_DIR / "policies"
BUNDLED_EXTRACT_SCRIPT = _BUNDLE_DIR / "extract_facts.py"

PROJECT_DATA_PATH = Path("policies/data.json")
OPA_QUERY = "data.a2kit.deny"


class RegoWrapperError(Exception):
    """Surfaceable error from the rego wrapper (missing toolchain, etc.)."""


def _check_environment(*, policies_dir: Path, extract_script: Path) -> None:
    if shutil.which("opa") is None:
        raise RegoWrapperError("opa not on PATH. Install with `brew install opa` (macOS) or see docs/dev/rego-toolchain.md.")
    if not extract_script.is_file():
        raise RegoWrapperError(f"extract script {extract_script} not found.")
    if not policies_dir.is_dir():
        raise RegoWrapperError(f"policies dir {policies_dir} not found.")


def _run_extract(paths: tuple[str, ...], out_path: Path, *, extract_script: Path) -> None:
    cmd = [sys.executable, str(extract_script), "--repo-root", ".", *paths, "-o", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 -- args composed from sys.executable + repo-local paths, not user input
    if proc.returncode != 0:
        raise RegoWrapperError(f"extract_facts.py failed (exit {proc.returncode}):\n{proc.stderr}")


@contextmanager
def _merged_bundle(policies_dir: Path, data_path: Path | None) -> Iterator[Path]:
    """Yield a temp bundle directory combining packaged policies + project data.

    OPA's ``--bundle`` + ``--data`` flag combo strips the data namespace
    when a bundle is loaded; merging into a single temp bundle directory
    is the reliable path (verified manually 2026-05-28).
    """
    with tempfile.TemporaryDirectory(prefix="a2kit-rego-") as tmpdir:
        tmp = Path(tmpdir)
        for rego in policies_dir.glob("*.rego"):
            (tmp / rego.name).write_bytes(rego.read_bytes())
        if data_path is not None and data_path.is_file():
            (tmp / "data.json").write_bytes(data_path.read_bytes())
        yield tmp


def _run_opa(facts_path: Path, *, policies_dir: Path, data_path: Path | None) -> list[dict[str, Any]]:
    with _merged_bundle(policies_dir, data_path) as bundle:
        cmd = [
            "opa",
            "eval",
            "--bundle",
            str(bundle),
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


def run_rego_policies(
    paths: tuple[str, ...],
    *,
    policies_dir: Path | None = None,
    extract_script: Path | None = None,
    data_path: Path | None = None,
) -> list[LintMessage]:
    """Run the OPA policy bundle against extracted facts. Returns findings.

    Defaults: ``policies_dir`` = packaged bundle, ``extract_script`` =
    packaged extractor, ``data_path`` = ``./policies/data.json`` if it
    exists in CWD (allowlist overlay). All three can be overridden.

    Raises ``RegoWrapperError`` for toolchain / pipeline failures (missing
    opa, missing scripts, malformed output). Policy `deny` findings are
    returned as `LintMessage` list; an empty list means clean.
    """
    policies_dir = policies_dir or BUNDLED_POLICIES_DIR
    extract_script = extract_script or BUNDLED_EXTRACT_SCRIPT
    if data_path is None and PROJECT_DATA_PATH.is_file():
        data_path = PROJECT_DATA_PATH

    _check_environment(policies_dir=policies_dir, extract_script=extract_script)
    if not paths:
        paths = ("src/",)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        facts_path = Path(tmp.name)
    try:
        _run_extract(paths, facts_path, extract_script=extract_script)
        findings = _run_opa(facts_path, policies_dir=policies_dir, data_path=data_path)
    finally:
        facts_path.unlink(missing_ok=True)
    return sorted(
        (_to_lint_message(f) for f in findings),
        key=lambda m: (m.filename, m.line, m.rule),
    )


@click.command("rego", help="Run OPA-based architectural policies (REGO-* rules).")
@click.option(
    "--policies-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Override the bundled policy directory.",
)
@click.option(
    "--extract-script",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Override the bundled fact extractor.",
)
@click.option(
    "--data",
    "data_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Override the project allowlist (default: ./policies/data.json if present).",
)
@click.argument("paths", nargs=-1)
def rego_cmd(
    paths: tuple[str, ...],
    policies_dir: Path | None,
    extract_script: Path | None,
    data_path: Path | None,
) -> None:
    try:
        findings = run_rego_policies(
            paths,
            policies_dir=policies_dir,
            extract_script=extract_script,
            data_path=data_path,
        )
    except RegoWrapperError as e:
        click.echo(f"a2kit lint rego: {e}", err=True)
        sys.exit(2)
    for f in findings:
        click.echo(f.format_concise())
    if findings:
        sys.exit(1)


__all__ = [
    "BUNDLED_EXTRACT_SCRIPT",
    "BUNDLED_POLICIES_DIR",
    "RegoWrapperError",
    "rego_cmd",
    "run_rego_policies",
]
