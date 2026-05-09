"""``install(server)`` returns the middleware and adds it to the server."""

from __future__ import annotations

import a2kit
from fastmcp import FastMCP

from a2kit.packages.mcp import build_mcp_server
from a2kit.packages.otel import OTelMiddleware, install


class _R(a2kit.Router):
    name = "demo"

    @a2kit.read("ping")
    async def ping(self) -> dict[str, int]:
        return {"x": 1}


def _build_server() -> FastMCP:
    app = a2kit.App("demo-app").use(_R())
    return build_mcp_server(app)


def test_install_returns_otel_middleware() -> None:
    server = _build_server()
    mw = install(server)
    assert isinstance(mw, OTelMiddleware)


def test_install_adds_to_server_middleware_chain() -> None:
    server = _build_server()
    before = list(getattr(server, "middleware", []))
    mw = install(server)
    after = list(getattr(server, "middleware", []))
    assert mw in after
    assert len(after) == len(before) + 1


def test_install_idempotent_per_call() -> None:
    """Each ``install`` adds a new middleware instance — the helper is the
    install hook, not a registry. Confirm that two calls do not error and
    register both middlewares."""
    server = _build_server()
    a = install(server)
    b = install(server)
    assert a is not b
    chain = list(getattr(server, "middleware", []))
    assert a in chain
    assert b in chain


def test_lazy_attribute_resolution() -> None:
    import a2kit.packages.otel as pkg

    # Public surface resolves through __getattr__
    assert pkg.install is install
    assert pkg.OTelMiddleware is OTelMiddleware
    assert callable(pkg.get_tracer)
    assert callable(pkg.get_meter)
