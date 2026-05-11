"""Transport-surface flag for tools.

A tool decorated with ``@a2kit.read(surfaces=Surface.CLI)`` is mounted only
on the CLI transport; an ``@a2kit.read(surfaces=Surface.MCP)`` tool is
mounted only by the MCP server. The default ``Surface.ALL`` makes the
tool visible on every transport an :class:`a2kit.App` exposes.

``Flag`` (not ``Enum``) so future surfaces compose: a tool exposed on CLI
and HTTP would be ``surfaces=Surface.CLI | Surface.HTTP``.
"""

from __future__ import annotations

from enum import Flag, auto

#: Metadata key under which the resolved Surface is stored on a tool's ``meta.extra``.
SURFACE_META_KEY = "a2kit.surfaces"


class Surface(Flag):
    """Transport surfaces a tool may be mounted on.

    ``CLI`` — the tool surfaces as a CLI subcommand built by
    :func:`a2kit.packages.cli.builder.build_full_cli`.

    ``MCP`` — the tool surfaces as an MCP tool registered on the
    :class:`a2kit.packages.mcp.server.MCPServer`.

    ``ALL`` — the default; visible on every supported transport.
    """

    CLI = auto()
    MCP = auto()
    ALL = CLI | MCP


__all__ = ["SURFACE_META_KEY", "Surface"]
