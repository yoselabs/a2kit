"""``McpSurface`` — the ``@app.mcp.<feature>(...)`` decorator accumulator.

Bound to an ``App`` via the ``App.mcp`` lazy property. Records the three
FastMCP-native feature kinds — ``tool``, ``prompt``, ``resource`` — that
have no equivalent on the FastAPI substrate.

Satisfies the ``Surface`` Protocol from ``packages/dispatch/surface``:
the dispatch-layer signature splitter discovers reserved types and
substrate-dep markers via the Surface's ClassVars rather than a
hardcoded substrate-string discriminator. Lookup of ``Context`` is
lazy — see ``reserved_types`` property.

At ``build_mcp_server`` time the recorded registrations are installed on
the FastMCP server alongside projection tools, each wrapped through
``install_substrate_signature(fn, "fastmcp", container)`` for a2kit DI.

``fastmcp_server`` is the escape hatch: once the FastMCP instance is
built, it is assigned here so authors can call
``add_middleware``/``add_transform``/etc. — rare, documented path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from a2kit.packages.dispatch import DecoratorSurface, SurfaceKind, fastmcp_reserved

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastmcp import FastMCP


McpFeatureKind = Literal["tool", "prompt", "resource"]


@dataclass(frozen=True)
class McpRegistration:
    """One ``@app.mcp.<feature>`` registration.

    ``fastmcp_kwargs`` is forwarded verbatim to the matching FastMCP API
    (``server.tool(...)``/``server.prompt(...)``/``server.resource(...)``);
    keys land as-is (``name``, ``description``, ``tags``, etc.).
    ``authorize`` is captured separately for the dispatch-time auth gate
    that ``add-auth`` enables.
    """

    kind: McpFeatureKind
    fn: Callable[..., Any]
    fastmcp_kwargs: dict[str, Any]  # noqa: AK214 -- forwarded verbatim to FastMCP; shape owned by upstream
    authorize: Callable[..., Any] | None = None


class McpSurface(DecoratorSurface[McpRegistration]):
    """The ``@app.mcp.tool``/``.prompt``/``.resource`` decorator family.

    Each decorator method returns a ``(**kwargs)`` decorator: stacking
    ``@app.mcp.tool(name="foo")`` on an async function records an
    :class:`McpRegistration`. ``build_mcp_server`` walks ``registrations``
    after the projection tools.

    ``expose=`` is rejected — the projection family owns multi-surface
    exposure; ``@app.mcp.*`` is single-surface by construction.
    """

    name: ClassVar[str] = "mcp"
    kind: ClassVar[SurfaceKind] = SurfaceKind.NETWORK
    # `substrate_dep_markers` is empty for FastMCP: there is no analog
    # to FastAPI's `Depends`/`Security` marker types on the MCP side.
    substrate_dep_markers: ClassVar[frozenset[type]] = frozenset()

    # `fastmcp_server` is set by `build_mcp_server` post-construction;
    # left as an instance attribute (not a ClassVar) so each App's
    # surface carries its own built server.
    fastmcp_server: FastMCP | None

    def __init__(self) -> None:
        super().__init__()
        self.fastmcp_server = None

    # `reserved_types` is a class-level descriptor that resolves to a
    # frozenset[type] on access. Declared as a property so the Protocol
    # contract is met at runtime without forcing a `fastmcp` import on
    # module load.
    @property
    def reserved_types(self) -> frozenset[type]:  # type: ignore[override]
        return fastmcp_reserved()

    def _decorator(self, kind: McpFeatureKind, **fastmcp_kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if "expose" in fastmcp_kwargs:
            msg = (
                f"@app.mcp.{kind}(expose=...): expose= is only valid on "
                f"projection decorators (@app.read/list/write). @app.mcp.* "
                f"is single-surface by construction."
            )
            raise TypeError(msg)
        authorize = fastmcp_kwargs.pop("authorize", None)

        def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._record(
                McpRegistration(
                    kind=kind,
                    fn=fn,
                    fastmcp_kwargs=fastmcp_kwargs,
                    authorize=authorize,
                )
            )
            return fn

        return _wrap

    def tool(self, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("tool", **kwargs)

    def prompt(self, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("prompt", **kwargs)

    def resource(self, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorator("resource", **kwargs)

    # --- `Surface` Protocol fulfilment ---------------------------------- #

    def bind(self, runtime: Any, descriptors: Any = None) -> Any:  # noqa: ARG002
        """Build the FastMCP server for ``runtime``, multiplex-ready.

        Delegates to :func:`a2kit.packages.mcp.server.build_mcp_server`
        with ``own_app_lifecycle=False`` — `bind` is the Surface entry
        point used by `build_parent_app`, which owns the single
        ``async with runtime:`` for the whole process. Callers needing
        the stdio path (sole owner of the lifecycle) call
        ``build_mcp_server`` directly.
        """
        from a2kit.packages.mcp.server import build_mcp_server

        return build_mcp_server(runtime, own_app_lifecycle=False)

    def install_di_bridge(self, runtime: Any, substrate_app: Any) -> None:  # noqa: ARG002
        """No-op hook: FastMCP DI bridge is installed inside ``build_mcp_server``.

        ``PrincipalMiddleware`` is mounted by the builder so the
        contextvar publication happens uniformly with non-Surface
        callers (the stdio ``serve`` path). Kept as a method to satisfy
        the Protocol contract and to give future bridges a hook.
        """
        return


def _mcp_surface_factory(_context: object) -> McpSurface:
    """Manifest factory for the built-in MCP surface. Always available."""
    return McpSurface()


from a2kit.packages._plugin import PluginManifest  # noqa: E402 -- below class def

MANIFEST = PluginManifest(name="mcp", protocol=McpSurface, factory=_mcp_surface_factory)


__all__ = ["MANIFEST", "McpFeatureKind", "McpRegistration", "McpSurface"]
