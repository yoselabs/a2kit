"""Pretty stderr operator sink — one human-readable line per emission.

Optional ANSI colour when ``sys.stderr.isatty()``. Format:
``[+12.3s] <kind:name> tool=<tool> payload=<...>``.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.packages.ldd.sinks._core import LddEmission

_ANSI = {
    "event": "\x1b[36m",  # cyan
    "report": "\x1b[35m",  # magenta
    "log": "\x1b[37m",  # white
    "reset": "\x1b[0m",
}


async def stderr_pretty_sink(emission: LddEmission, /) -> None:
    """Write one pretty line for ``emission`` to stderr."""
    use_colour = sys.stderr.isatty()
    secs = emission.elapsed_ms / 1000.0
    head = f"[+{secs:>6.3f}s]"
    label = f"{emission.kind}:{emission.name}"
    if use_colour:
        colour = _ANSI.get(emission.kind, "")
        label = f"{colour}{label}{_ANSI['reset']}"
    tool = f" tool={emission.tool_name}" if emission.tool_name else ""
    payload = f" payload={emission.payload!r}" if emission.payload else ""
    print(f"{head} {label}{tool}{payload}", file=sys.stderr, flush=True)  # noqa: T201


__all__ = ["stderr_pretty_sink"]
