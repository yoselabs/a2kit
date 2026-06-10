"""Runtime tool-subset selection — env var (``A2KIT_TOOLS``) + CLI flag.

A first-class operator surface for "expose only these tools on this server."
Resolved once at server-build / CLI-build time, never per-request. Filters
the descriptor set BEFORE MCP server registration and Click subcommand
registration; cannot re-enable tools filtered out at compile time by an
unlisted surface state (``surfaces={...: "unlisted"}``) — it is a SUBSET
selector, not an override.

When both env var and CLI flag are set, the **intersection** wins (the
more restrictive set survives). When neither is set, every
compile-time-visible tool is exposed (current default behavior).

Spec: ``openspec/specs/runtime-tool-selection/spec.md``. Designed in
change ``a2web-handoff-prep``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

ENV_VAR: Final[str] = "A2KIT_TOOLS"


class ToolSelectionError(ValueError):
    """A runtime selector named a tool that is not in the App's surface.

    Raised by :func:`resolve_selector` when the env var or CLI flag carries
    an unknown name. Listing the valid names in the message helps operators
    fix typos quickly.
    """


def parse_selector(raw: str | None) -> frozenset[str] | None:
    """Parse a comma-separated tool-name list. Returns ``None`` when unset/empty.

    ``parse_selector(None)`` → ``None`` (no selector active)
    ``parse_selector("")`` → ``None`` (empty string treated as unset)
    ``parse_selector("ask")`` → ``frozenset({"ask"})``
    ``parse_selector("ask,refresh")`` → ``frozenset({"ask", "refresh"})``
    ``parse_selector(" ask , refresh ")`` → ``frozenset({"ask", "refresh"})``
      (whitespace around names stripped).
    """
    if raw is None:
        return None
    cleaned = [name.strip() for name in raw.split(",") if name.strip()]
    if not cleaned:
        return None
    return frozenset(cleaned)


def resolve_selector(
    *,
    env: str | None = None,
    cli_arg: str | None = None,
) -> frozenset[str] | None:
    """Combine env var + CLI flag selectors via intersection. Returns ``None``
    when neither is set.

    When both are set, the result is their set intersection — the more
    restrictive wins. When only one is set, that one's parsed set wins.
    The caller is responsible for validating the resulting names against
    the App's actual tool surface (see :func:`validate_selector`).

    ``env`` defaults to ``os.environ[ENV_VAR]`` if ``None``. Pass an
    explicit string (or empty string) for tests.
    """
    env_value = os.environ.get(ENV_VAR) if env is None else env
    env_set = parse_selector(env_value)
    cli_set = parse_selector(cli_arg)
    if env_set is None and cli_set is None:
        return None
    if env_set is None:
        return cli_set
    if cli_set is None:
        return env_set
    return env_set & cli_set


def validate_selector(
    selector: frozenset[str],
    *,
    available: Iterable[str],
) -> None:
    """Raise :class:`ToolSelectionError` if any name in ``selector`` is not
    in ``available``. The message names the unknown(s) and lists valid names.

    ``available`` is the set of tool names that would be exposed without
    any selector — i.e. compile-time-visible tools only. Unlisted tools
    (``surfaces={...: "unlisted"}``) MUST be excluded from ``available``
    before calling; that's how the selector "cannot re-enable a hidden
    tool" invariant is enforced.
    """
    avail_set = frozenset(available)
    unknown = selector - avail_set
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        valid_list = ", ".join(sorted(avail_set)) or "(none)"
        msg = (
            f"runtime tool selection includes unknown tool name(s): {unknown_list}. "
            f"Valid tool names for this App: {valid_list}. "
            f"(Hidden tools cannot be re-enabled via {ENV_VAR}/--tools=.)"
        )
        raise ToolSelectionError(msg)


__all__ = [
    "ENV_VAR",
    "ToolSelectionError",
    "parse_selector",
    "resolve_selector",
    "validate_selector",
]
