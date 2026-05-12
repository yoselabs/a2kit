"""Google-style docstring parameter description extractor.

Used by `_stamp` to pull per-parameter descriptions from a tool's
docstring, eliminating the need for `Annotated[T, a2kit.Param(...)]`
wrappers when the docstring already documents the param.

Supports Google-style ``Args:`` / ``Arguments:`` / ``Parameters:``
sections only. Numpy and Sphinx/reST formats are explicit non-goals
— Google is the most common in Python tooling and the only one this
helper recognises.

Precedence rule (applied by callers, not here): explicit
``Annotated[T, FieldInfo(description=...)]`` wins over docstring.
This helper just reads what the docstring says — never raises;
parse anomalies return an empty mapping.
"""

from __future__ import annotations

import contextlib
import inspect
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

_HEADER_RE = re.compile(r"^(args|arguments|parameters)\s*:\s*$", re.IGNORECASE)
_STOP_RE = re.compile(
    r"^(returns|raises|yields|examples?|notes?|attributes|see also)\s*:\s*$",
    re.IGNORECASE,
)
_ENTRY_RE = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?:\([^)]*\))?\s*:\s*(?P<desc>.*)$")


def extract_param_descriptions(doc: str | None) -> Mapping[str, str]:
    """Return ``{param_name: description}`` parsed from a Google-style docstring.

    Returns an empty mapping if ``doc`` is None/empty, if no ``Args:``
    section is found, or on any parse anomaly. Never raises.
    """
    if not doc:
        return {}
    with contextlib.suppress(Exception):
        cleaned = inspect.cleandoc(doc)
        return _parse(cleaned)
    return {}


def _parse(doc: str) -> dict[str, str]:
    lines = doc.splitlines()
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        if _HEADER_RE.match(lines[i].strip()):
            i = _consume_section(lines, i + 1, out)
            continue
        i += 1
    return out


def _consume_section(lines: list[str], start: int, out: dict[str, str]) -> int:
    i = start
    current_name: str | None = None
    current_desc_parts: list[str] = []
    entry_indent: int | None = None

    def flush() -> None:
        nonlocal current_name, current_desc_parts
        if current_name is not None:
            text = " ".join(p.strip() for p in current_desc_parts if p.strip())
            if text:
                out[current_name] = text
        current_name = None
        current_desc_parts = []

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        if _STOP_RE.match(stripped) or _HEADER_RE.match(stripped):
            break
        # Determine line indent.
        indent = len(raw) - len(raw.lstrip())
        if entry_indent is None or indent <= entry_indent:
            # New entry candidate.
            m = _ENTRY_RE.match(stripped)
            if m is None:
                # Not an entry; stop the section.
                break
            flush()
            current_name = m.group("name")
            current_desc_parts = [m.group("desc")]
            entry_indent = indent
        else:
            # Continuation of the current entry.
            current_desc_parts.append(stripped)
        i += 1
    flush()
    return i


__all__ = ["extract_param_descriptions"]
