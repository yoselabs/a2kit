"""CLI is a Surface (ADR 0028 Wave 1) — kind=LOCAL, bind owns the Typer build."""

from __future__ import annotations

import click

import a2kit
from a2kit.packages.dispatch.surface import Surface, SurfaceKind


def test_surfacekind_members() -> None:
    assert {m.name for m in SurfaceKind} == {"NETWORK", "LOCAL"}


def test_network_surfaces_declare_network_kind() -> None:
    from a2kit.packages.http.api import ApiSurface
    from a2kit.packages.mcp.surface import McpSurface

    assert McpSurface.kind is SurfaceKind.NETWORK
    assert ApiSurface.kind is SurfaceKind.NETWORK


def test_cli_surface_satisfies_protocol() -> None:
    from a2kit.packages.cli.surface import CliSurface

    surf = CliSurface()
    assert isinstance(surf, Surface)
    assert surf.name == "cli"
    assert CliSurface.kind is SurfaceKind.LOCAL


def test_cli_surface_bind_builds_command(app: a2kit.App) -> None:
    from click.testing import CliRunner

    from a2kit.packages.cli.surface import CliSurface

    command = CliSurface().bind(app)
    assert isinstance(command, click.Command)
    out = CliRunner().invoke(command, ["--help"]).output
    assert "tasks" in out  # router slug
    assert "schema" in out
    assert "serve" in out


def test_app_cli_accessor_is_idempotent(app: a2kit.App) -> None:
    from a2kit.packages.cli.surface import CliSurface

    first = app.cli
    assert isinstance(first, CliSurface)
    assert app.cli is first  # idempotent — same instance


def test_default_surface_set_excludes_local_cli() -> None:
    """LOCAL CLI surface does not join the network mount set."""
    from a2kit.runtime import build

    runtime = build(a2kit.App("t"), surfaces=a2kit.compose_default_surfaces())
    assert runtime.surfaces.names() == ("mcp", "api")
