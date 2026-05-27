"""Opt-in OpenTelemetry adapter for a2kit-built FastMCP servers.

Install with::

    pip install 'a2kit[otel]'

Then wire it into a FastMCP server built via :func:`a2kit.packages.mcp.build_mcp_server`::

    from a2kit.packages.mcp import build_mcp_server
    from a2kit.packages.otel import install

    server = build_mcp_server(app)
    install(server)

The :class:`OTelMiddleware` wraps every tool call in an OTel span whose
attributes are pulled from :class:`a2kit.metadata.A2KitMeta` (tool name,
verb, router, tags) plus the FastMCP-side request id. Optional metric
counters track call volume and status.

a2kit core stays OTel-free. This package lazily imports
``opentelemetry-api`` at first use and raises a friendly ``ImportError``
if the optional deps are missing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit._lazy_module import lazy_attr, lazy_dir

if TYPE_CHECKING:
    from a2kit.packages.otel.middleware import OTelMiddleware


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "install": ("a2kit.packages.otel.middleware", "install"),
    "OTelMiddleware": ("a2kit.packages.otel.middleware", "OTelMiddleware"),
    "get_tracer": ("a2kit.packages.otel.tracer", "get_tracer"),
    "get_meter": ("a2kit.packages.otel.tracer", "get_meter"),
}


__getattr__ = lazy_attr(__name__, _LAZY_ATTRS)
__dir__ = lazy_dir(globals(), _LAZY_ATTRS)
del lazy_attr, lazy_dir


__all__ = ["OTelMiddleware", "get_meter", "get_tracer", "install"]
