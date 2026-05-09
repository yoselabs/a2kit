from __future__ import annotations

from typing import Any

import click


class LazyGroup(click.Group):
    def __init__(self, *args: Any, lazy_subcommands: dict[str, str] | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self._lazy = lazy_subcommands or {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted({*super().list_commands(ctx), *self._lazy})

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        if cmd_name in self._lazy:
            target = self._lazy[cmd_name]
            mod_path, attr = target.rsplit(":", 1)
            from importlib import import_module

            return getattr(import_module(mod_path), attr)
        return super().get_command(ctx, cmd_name)


@click.group(
    cls=LazyGroup,
    lazy_subcommands={
        "lint": "a2kit.packages.lint.cli:main",
        "connections": "a2kit.packages.connections.cli:connections_group",
    },
    help="a2kit developer CLI — lint and manage saved connections.",
)
def main() -> None:
    """a2kit developer CLI."""


if __name__ == "__main__":
    main()
