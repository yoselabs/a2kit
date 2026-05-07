"""Shared lint types and helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LintMessage:
    """Single lint finding from a static rule."""

    rule: str
    filename: str
    line: int
    col: int
    message: str

    def format_concise(self) -> str:
        """ruff-concise format: `path:line:col: RULE message`."""
        return f"{self.filename}:{self.line}:{self.col}: {self.rule} {self.message}"


def parse_noqa(source: str) -> dict[int, set[str]]:
    """Map line number → set of rule codes suppressed via `# noqa: CODE` on that line.

    `# noqa` (no codes) suppresses everything; we use the sentinel `"*"`.
    """
    out: dict[int, set[str]] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        idx = line.find("# noqa")
        if idx == -1:
            continue
        rest = line[idx + len("# noqa") :].lstrip()
        if rest.startswith(":"):
            codes = {c.strip() for c in rest[1:].split(",") if c.strip()}
            out[i] = codes
        else:
            out[i] = {"*"}
    return out


def suppressed(noqa_map: dict[int, set[str]], rule: str, line: int) -> bool:
    codes = noqa_map.get(line)
    if not codes:
        return False
    return "*" in codes or rule in codes
