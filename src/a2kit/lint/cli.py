"""CLI entry: `a2kit lint` (static) and `a2kit check` (runtime).

Runs as `uvx a2kit lint paths...` or `uvx a2kit check --import path:server`.
Output mirrors ruff's concise format. Exit non-zero on findings.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any

from a2kit.lint.runtime import run_runtime_checks
from a2kit.lint.static import run_static_rules


def _expand_paths(inputs: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        elif p.is_file():
            out.append(p)
    return out


def _import_target(spec: str) -> Any:
    """Resolve `module.path:attribute` to a Python object."""
    if ":" not in spec:
        msg = f"--import requires module:attr, got {spec!r}"
        raise ValueError(msg)
    mod, attr = spec.split(":", 1)
    module = importlib.import_module(mod)
    return getattr(module, attr)


def cmd_lint(args: argparse.Namespace) -> int:
    paths = _expand_paths(args.paths)
    findings = run_static_rules(paths, disabled=args.disabled or [])
    for f in findings:
        print(f.format_concise())  # noqa: T201
    return 1 if findings else 0


def cmd_check(args: argparse.Namespace) -> int:
    server = _import_target(args.import_target)
    config: dict[str, Any] = {}
    if args.snapshot_dir:
        config["snapshot_dir"] = args.snapshot_dir
    if args.total_budget is not None:
        config["total_budget"] = args.total_budget
    findings = run_runtime_checks(server, config=config, disabled=args.disabled or [])
    for f in findings:
        print(f.format_concise())  # noqa: T201
    return 1 if findings else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a2kit", description="a2kit lint + check")
    sub = parser.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="Run static lint rules")
    lint.add_argument("paths", nargs="+", help="Files or directories to lint")
    lint.add_argument("--disabled", action="append", default=[], help="Disable rule by code")
    lint.set_defaults(func=cmd_lint)

    check = sub.add_parser("check", help="Run runtime checks against an importable server")
    check.add_argument("--import", dest="import_target", required=True, help="module:attr to import")
    check.add_argument("--snapshot-dir", default=None, help="Path to schema snapshots directory")
    check.add_argument("--total-budget", type=int, default=None, help="Total snapshot size budget in bytes")
    check.add_argument("--disabled", action="append", default=[], help="Disable rule by code")
    check.set_defaults(func=cmd_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    ns = parser.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
