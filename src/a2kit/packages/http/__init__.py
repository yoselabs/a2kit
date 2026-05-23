"""HTTP surface — FastAPI sub-app for the ``serve --transport=http`` mount.

Per ``http-surface`` capability: projection tools registered on
``App`` (via ``@app.read``/``@app.list``/``@app.write``) are exposed
on the FastAPI sub-app as ``POST /api/<tool_name>`` routes. Author-
written ``@app.api.<method>(...)`` routes appear alongside them at
their declared paths.

Both kinds of registration share one mechanism: the wrapper from
``a2kit.packages.dispatch.substrate.install_substrate_signature``.
The wrapper exposes only the substrate-routed params (FastAPI-native
reserved types + wire params) on the surface signature and resolves
a2kit DI types from the per-call ``Container.call_scope`` inside the
wrapper body.

Imported only on the ``serve --transport=http`` path. ``import a2kit``
does not pull this module, nor ``fastapi``.
"""

from __future__ import annotations

from a2kit.packages.http.api import ApiSurface
from a2kit.packages.http.build import build_http_app

__all__ = ["ApiSurface", "build_http_app"]
