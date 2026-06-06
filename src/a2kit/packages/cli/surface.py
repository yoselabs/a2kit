"""``CliSurface`` — the CLI as a first-class ``Surface`` (ADR 0028 Wave 1).

Making the CLI a ``Surface`` puts MCP, HTTP, and CLI on one ``bind(...)``
composition model, so Wave 2's homomorphism lands on a uniform set of
surfaces instead of special-casing the CLI.

``kind = LOCAL``: the CLI is a process-local transport. ``serve-topology``
mounts only ``NETWORK`` surfaces into the parent ASGI app, so the LOCAL
CLI never joins the network mount set — it is materialized on demand by
``a2kit.run`` through ``CliSurface().bind(runtime)``.

Cold-start: this module imports only stdlib + the substrate-free
dispatch layer at top level. ``typer`` is pulled only when ``bind`` runs
(it delegates to ``build_full_cli``, which imports typer inside its body),
so ``import a2kit`` stays typer-free. ``App.cli`` ``importlib``-loads this
module lazily, mirroring ``App.api`` / ``App.mcp``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from a2kit.packages.dispatch import SurfaceKind


class CliSurface:
    """The CLI surface, peer of ``McpSurface`` / ``ApiSurface``.

    ``bind`` owns the Typer build: it delegates to ``build_full_cli``,
    which composes the per-router sub-Typers, the ``schema`` / ``serve`` /
    ``code`` / ``health`` subcommands, the ``A2KIT_TOOLS`` selection seam,
    and the vendored-click ``add_command`` attachment guard (ADR 0028
    decision 1 — the typer >= 0.26 compat shim has exactly one home, on
    the CLI build path that ``bind`` owns).
    """

    name: ClassVar[str] = "cli"
    kind: ClassVar[SurfaceKind] = SurfaceKind.LOCAL
    reserved_types: ClassVar[frozenset[type]] = frozenset()
    substrate_dep_markers: ClassVar[frozenset[type]] = frozenset()

    def bind(self, runtime: Any, descriptors: Any = None) -> Any:  # noqa: ARG002 -- CLI reads descriptors off runtime.tools(); param kept for protocol uniformity
        """Assemble the top-level CLI ``click.Command`` for ``runtime``.

        Accepts a compose-phase ``App`` or a built ``AppRuntime`` (``build``
        is idempotent). ``descriptors`` is accepted for protocol
        uniformity with the network surfaces; the CLI reads its tools off
        ``runtime.tools()`` inside the builder, so it is ignored here.
        """
        from a2kit.packages.cli.builder import build_full_cli

        return build_full_cli(runtime)

    def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:
        """No-op: the CLI resolves DI per-invocation through the existing
        ``invoke_tool_sync`` path, so there is no separate bridge to
        install. Present to satisfy the ``Surface`` protocol uniformly.
        """


__all__ = ["CliSurface"]
