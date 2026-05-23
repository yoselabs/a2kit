"""``McpSurface`` — the ``@app.mcp.<feature>(...)`` decorator accumulator.

Bound to an ``App`` via the ``App.mcp`` lazy property. Records the three
FastMCP-native feature kinds — ``tool``, ``prompt``, ``resource`` — that
have no equivalent on the FastAPI substrate.

At ``build_mcp_server`` time the recorded registrations are installed on
the FastMCP server alongside projection tools, each wrapped through
``install_substrate_signature(fn, "fastmcp", container)`` for a2kit DI.

``fastmcp_server`` is the escape hatch: once the FastMCP instance is
built, it is assigned here so authors can call
``add_middleware``/``add_transform``/etc. — rare, documented path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

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
    fastmcp_kwargs: dict[str, Any]
    authorize: Callable[..., Any] | None = None


@dataclass
class McpSurface:
    """The ``@app.mcp.tool``/``.prompt``/``.resource`` decorator family.

    Each decorator method returns a ``(**kwargs)`` decorator: stacking
    ``@app.mcp.tool(name="foo")`` on an async function records an
    :class:`McpRegistration`. ``build_mcp_server`` walks ``registrations``
    after the projection tools.

    ``expose=`` is rejected — the projection family owns multi-surface
    exposure; ``@app.mcp.*`` is single-surface by construction.
    """

    registrations: list[McpRegistration] = field(default_factory=list)
    fastmcp_server: FastMCP | None = None

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
            self.registrations.append(
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


__all__ = ["McpFeatureKind", "McpRegistration", "McpSurface"]
