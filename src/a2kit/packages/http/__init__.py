"""HTTP surface — FastAPI sub-app for the ``serve --transport=http`` mount.

Per ``http-surface`` capability: projection tools registered on
``App`` (via ``@app.read``/``@app.list``/``@app.write``) are exposed
on the FastAPI sub-app as ``POST /api/<tool_name>`` routes. Author-
written ``@app.api.<method>(...)`` routes appear alongside them at
their declared paths.

Both kinds of registration share one mechanism: the wrapper from
``a2kit.packages.dispatch.install_substrate_signature``. The wrapper
exposes only the substrate-routed params (FastAPI-native reserved
types + wire params) on the surface signature and resolves a2kit DI
types from the per-call ``Container.call_scope`` inside the wrapper
body.

**Cold start**: ``import a2kit.packages.http`` MUST NOT pull
``fastapi``. ``ApiSurface`` (a plain dataclass) is reachable as
``http.api.ApiSurface``; ``build_http_app`` is exposed via PEP 562
``__getattr__`` so accessing it on the package object triggers the
deferred ``fastapi``-importing ``build`` module load on demand only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2kit._lazy_module import lazy_attr
from a2kit.packages.http.api import ApiSurface

if TYPE_CHECKING:
    from a2kit.packages.http.build import build_http_app


# NOTE: Surface registration is no longer performed at import time. Per
# `bootstrap-surfaces-explicit`, surfaces are composed explicitly at
# `runtime.build()` time from its `surfaces=` tuple (defaulting to the
# bundled `McpSurface` + `ApiSurface` pair). Importing this package has
# zero side effects on any registry.


_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "build_http_app": ("a2kit.packages.http.build", "build_http_app"),
}

__getattr__ = lazy_attr(__name__, _LAZY_ATTRS)
del lazy_attr


__all__ = ["ApiSurface", "build_http_app"]
