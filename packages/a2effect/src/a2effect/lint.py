from __future__ import annotations

import ast
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2effect._lint._core import LintMessage


def discover_rules() -> dict[str, callable]:
    eps = entry_points(group="a2lint.rules")
    return {ep.name: ep.load() for ep in eps}


def lint_path(target: Path) -> list[LintMessage]:
    rules = discover_rules()
    files = [target] if target.is_file() else [p for p in target.rglob("*.py") if p.is_file()]
    messages: list[LintMessage] = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for rule in rules.values():
            messages.extend(rule(tree, path=path, source=source))
    return messages


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        sys.stderr.write("usage: python -m a2effect.lint <path> [<path>...]\n")
        return 2
    all_messages: list[LintMessage] = []
    for arg in args:
        target = Path(arg).resolve()
        if not target.exists():
            sys.stderr.write(f"a2effect.lint: path not found: {arg}\n")
            return 2
        all_messages.extend(lint_path(target))
    for msg in all_messages:
        print(msg.format())  # noqa: T201 — CLI shim output is the contract
    return 1 if any(m.severity == "error" for m in all_messages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
