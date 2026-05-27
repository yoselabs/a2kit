"""Click entry point for the ``a2kit lint`` command.

Exported callable: ``main`` — a ``click.Group`` registered into the top-level
``a2kit`` LazyGroup as the ``lint`` subcommand. Two subcommands:

- ``a2kit lint static <paths>...`` — run AST rules.
- ``a2kit lint runtime --import module:server`` — run runtime checks.

This module imports ONLY stdlib + click + a2kit.packages.lint.{static,runtime}.
No fastmcp, no a2kit runtime concepts.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from a2kit.packages.lint._import import import_target
from a2kit.packages.lint.rego import rego_cmd
from a2kit.packages.lint.runtime import run_runtime_checks
from a2kit.packages.lint.static import run_static_rules


def _expand_paths(inputs: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            out.append(p)
    return out


def _import_target(spec: str) -> Any:
    """Click-flavoured wrapper around ``import_target`` — re-raises as ``BadParameter``."""
    try:
        return import_target(spec)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


@click.group(name="lint", help="Static + runtime lint for a2kit MCP servers.")
def main() -> None:
    """``a2kit lint`` group root."""


@main.command("static", help="Run static AST rules over the given paths.")
@click.argument("paths", nargs=-1, required=True)
@click.option(
    "--disabled",
    "disabled",
    multiple=True,
    default=(),
    help="Disable a rule by code (repeat for multiple).",
)
def static_cmd(paths: tuple[str, ...], disabled: tuple[str, ...]) -> None:
    expanded = _expand_paths(paths)
    findings = run_static_rules(expanded, disabled=disabled)
    for f in findings:
        click.echo(f.format_concise())
    if findings:
        sys.exit(1)


@main.command("runtime", help="Run runtime checks against an importable server.")
@click.option("--import", "import_target", required=True, help="module:attr to import")
@click.option("--snapshot-dir", default=None, help="Path to schema snapshots directory")
@click.option("--total-budget", type=int, default=None, help="Total snapshot size budget in bytes")
@click.option(
    "--disabled",
    "disabled",
    multiple=True,
    default=(),
    help="Disable a check by code (repeat for multiple).",
)
def runtime_cmd(
    import_target: str,
    snapshot_dir: str | None,
    total_budget: int | None,
    disabled: tuple[str, ...],
) -> None:
    server = _import_target(import_target)
    config: dict[str, Any] = {}
    if snapshot_dir:
        config["snapshot_dir"] = snapshot_dir
    if total_budget is not None:
        config["total_budget"] = total_budget
    findings = run_runtime_checks(server, config=config, disabled=disabled)
    for f in findings:
        click.echo(f.format_concise())
    if findings:
        sys.exit(1)


main.add_command(rego_cmd)


if __name__ == "__main__":
    main()
