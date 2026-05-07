"""Docstring helpers — canonical phrasings for recurring tool params.

Addresses a real-world drift problem: every tool that takes a `connection` param
re-explains "this is the saved connection name, not a project key" in slightly
different wording. The agent ends up confused because the phrasing drifts. One
canonical helper means one paraphrase across the whole MCP.

Public API:

- `connection_param_doc(name="connection", *, cli="a2kit", example="prod", custom_suffix=None)`
  Returns the canonical paragraph. Composable into f-strings inside docstrings.
"""

from __future__ import annotations


def connection_param_doc(
    name: str = "connection",
    *,
    cli: str = "a2kit",
    example: str = "prod",
    custom_suffix: str | None = None,
) -> str:
    """Canonical sentence for the connection parameter — eliminates per-tool drift.

    Returns a one-liner suitable for embedding in a tool docstring via f-string.

    Example output:
        connection: Saved a2kit connection name (e.g. 'prod'), not a project key
        or ID. Use `a2kit connections list` to see available names.

    Override `cli` / `example` / append a domain-specific clarification via
    `custom_suffix` ("This is NOT a Jira project key.").
    """
    base = (
        f"{name}: Saved {cli} connection name (e.g. {example!r}), not a project key or ID. "
        f"Use `{cli} connections list` to see available names."
    )
    if custom_suffix:
        base = f"{base} {custom_suffix}"
    return base


__all__ = ["connection_param_doc"]
