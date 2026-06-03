"""In-process test client — real FastMCP transport, capture via handlers.

Drives an in-memory ``fastmcp.Client(transport=build_mcp_server(app))``
so every tool dispatch goes through the production MCP wrapper chain
(dispatch-hook signature rewrite, call-scope binding,
fastmcp.Context injection, ``mcp-structured-wire-error-envelope``
error path). Captured emissions (events, reports, logs, progress) are
surfaced via client-side ``log_handler`` / ``progress_handler``
notifications, fanned out by the ``a2kit_kind`` marker the log wire
format carries.

Replaces the previous ``_CapturingContext(StderrToolContext)`` design,
which never exercised the MCP wrapper chain and missed every bug that
lived between dispatch-hook signature rewriting and FastMCP binding
(see ``fix-mcp-dispatch-strips-ctx`` and
``mcp-structured-wire-error-envelope`` for the production fallout).

Cold-start preserving: this module is lazy-imported via
:mod:`a2kit.testing` and never pulled by a bare ``import a2kit``.

Example::

    async with a2kit.testing.client(app) as c:
        result = await c.invoke("tasks.create_project", name="P1")
        assert any(e["name"] == "ProjectCreated" for e in c.events)
        assert c.progress[-1] == (1.0, 1.0)
        assert c.render_as("json", result) == {...}

**Return shape.** ``invoke()`` returns ``result.data`` from
``fastmcp.Client.call_tool``, which is the FastMCP-unmarshaled form
of the tool's return value. For tools returning user-declared
dataclasses or BaseModels, FastMCP synthesizes a Pydantic-validated
copy with field-equivalent shape (same field names + values) but a
distinct class identity. Tests that asserted on identity equality of
user-declared types must migrate to field-wise comparison (e.g.
``result[0].id == 1``) or ``model_dump()`` equality.

**Exception propagation.** Tool-body exceptions surface as
``fastmcp.exceptions.ToolError`` carrying the a2kit-owned structured
envelope from ``mcp-structured-wire-error-envelope`` —
``json.loads(str(exc)) == {"class": ..., "message": ..., [traceback]}``.
Tests asserting on Python exception classes parse the JSON envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from a2kit.packages.formatter import FormatHint, format_response
from a2kit.packages.mcp import build_mcp_server

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.tool import ToolDescriptor


class TestClient:
    """In-process test client backed by real FastMCP in-memory transport.

    Manages two resources for the ``async with`` lifetime: the
    ``fastmcp.FastMCP`` server (built from the App, lifecycle included)
    and an in-memory ``fastmcp.Client`` connected to it. FastMCP drives
    the server's lifespan, so the App's ``async with app:`` lifecycle
    enters automatically.
    """

    #: Methods renamed in prior releases. Accessing the old name raises
    #: ``TypeError`` with an embedded migration hint via
    #: :meth:`__getattr__`. No alias is provided.
    _MIGRATED_NAMES: ClassVar[dict[str, str]] = {"call": "invoke"}

    #: Methods removed outright (no rename target). Accessing the old
    #: name raises ``TypeError`` with the full migration recipe.
    _REMOVED_NAMES: ClassVar[dict[str, str]] = {
        "override": (
            "TestClient.override(T, fake) was removed in v0.40. Test overrides "
            "are re-build, not post-seal mutation: construct a fresh a2kit.App "
            "and provide the fake last (provide is last-write-wins) — "
            "`app = a2kit.App(name).provide(T, fake)`. "
            "See ADR 0017 / CHANGELOG: internalize-app-runtime."
        ),
    }

    def __getattr__(self, name: str) -> Any:
        cls = type(self)
        migrated = cls._MIGRATED_NAMES
        if name in migrated:
            new = migrated[name]
            raise TypeError(f"TestClient.{name}(...) was renamed to TestClient.{new}(...). Update the call site; no alias is provided.")
        removed = cls._REMOVED_NAMES
        if name in removed:
            raise TypeError(removed[name])
        raise AttributeError(f"'TestClient' object has no attribute {name!r}")

    def __init__(self, app: App) -> None:
        self.app = app
        self.events: list[dict[str, Any]] = []
        self.progress: list[tuple[float, float | None]] = []
        self.progress_with_message: list[tuple[float, float | None, str | None]] = []
        self.logs: list[dict[str, Any]] = []
        self.reports: list[dict[str, Any]] = []
        self._client: Any = None
        self._client_cm: Any = None

    async def __aenter__(self) -> TestClient:
        from fastmcp import Client  # noqa: A2K-IMPORT-DISCIPLINE

        # `build_mcp_server` is the finisher: it builds the App into a
        # sealed runtime internally (validates + freezes the container),
        # exactly as `run` does. The test client never builds explicitly.
        # `code_mode=False`: the in-process test client drives tools
        # directly; the code-execution transform would collapse the tool
        # catalog it inspects. Tests of code mode use `fastmcp.Client`.
        server = build_mcp_server(self.app, code_mode=False)
        # Re-enable ``_meta.*`` tools (production hides them from agent
        # `list_tools` via ``server.disable(tags={"_meta"})``; tests need
        # to invoke ``_meta.health`` directly).
        server.enable(tags={"_meta"})
        self._client_cm = Client(
            transport=server,
            log_handler=self._on_log,
            progress_handler=self._on_progress,
        )
        self._client = await self._client_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client_cm is not None:
            try:
                await self._client_cm.__aexit__(exc_type, exc, tb)
            finally:
                self._client_cm = None
                self._client = None

    # ---------- capture handlers (server -> client notifications) -------- #

    async def _on_log(self, message: Any) -> None:
        """Fan-out by the ``a2kit_kind`` marker in the wire payload.

        FastMCP delivers ``message.data == {"msg": <ctx.log message>,
        "extra": <ctx.log extra dict>}`` on the client side. We pull
        `a2kit_kind` out of ``extra`` and route to ``events`` /
        ``reports`` / ``logs``.

        The wire-side ``extra`` carries a2kit-internal keys prefixed
        with ``a2kit_`` (e.g. ``a2kit_name``, ``a2kit_payload``,
        ``a2kit_elapsed_ms``) to dodge Python ``LogRecord`` reserved
        attribute collisions. We un-prefix them to the public capture
        shape so test consumers see ``c.events[0]["name"]`` etc.
        """
        data = getattr(message, "data", None) or {}
        if not isinstance(data, dict):
            return
        extra = dict(data.get("extra") or {})
        wire_msg = data.get("msg", "")
        kind = extra.pop("a2kit_kind", None)
        level_norm = self._normalize_level(getattr(message, "level", "info"))

        if kind == "event":
            self.events.append(
                {
                    "name": extra.get("a2kit_name", wire_msg),
                    "payload": extra.get("a2kit_payload", {}),
                    "elapsed_ms": extra.get("a2kit_elapsed_ms"),
                }
            )
            return
        if kind == "report":
            self.reports.append(
                {
                    "type": extra.get("a2kit_type", wire_msg),
                    "body": extra.get("a2kit_payload", {}),
                    "elapsed_ms": extra.get("a2kit_elapsed_ms"),
                }
            )
            return

        # Plain log line — user-supplied fields plus framework-injected
        # `a2kit_elapsed_ms`. Strip the prefix on `elapsed_ms`; leave
        # user fields untouched.
        elapsed = extra.pop("a2kit_elapsed_ms", None)
        self.logs.append(
            {
                "level": level_norm,
                "msg": wire_msg,
                "fields": extra,
                "elapsed_ms": elapsed,
            }
        )

    async def _on_progress(self, progress: float, total: float | None = None, message: str | None = None) -> None:
        self.progress.append((progress, total))
        self.progress_with_message.append((progress, total, message))

    @staticmethod
    def _normalize_level(level_raw: Any) -> str:
        """Map FastMCP MCP log levels to the log wire-shorthand the
        legacy capture surfaced (``INFO`` / ``WARN`` / ``ERROR`` /
        ``DEBUG``)."""
        s = str(level_raw).lower()
        if s == "warning":
            return "WARN"
        return s.upper()

    # ----------------------------------- public test surface -------------- #

    def tools(self) -> list[ToolDescriptor]:
        """Return tool descriptors, sorted by name."""
        return sorted(self.app.tools(), key=lambda d: d.name)

    def render_as(self, fmt: str, value: Any) -> Any:
        """Render ``value`` through the same formatter the transports use."""
        response = format_response(value, format_hint=cast("FormatHint", fmt))
        return response.data

    async def call_wire(
        self,
        tool_name: str,
        *,
        connection: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``tool_name`` and return the **wire-encoded** payload.

        Uses FastMCP's ``structured_content`` (clean dict / list-of-dicts)
        as the formatter input rather than ``.data`` (FastMCP-synthesized
        types that don't satisfy ``isinstance(x, BaseModel)`` or
        ``isinstance(x, dict)``). For list returns FastMCP wraps as
        ``{"result": [...]}`` per its convention; unwrap to the raw list
        so TSV formatting can iterate rows.
        """
        if self._client is None:
            raise RuntimeError("TestClient must be used as `async with client(app) as c:` before calling call_wire().")
        descriptor = self._descriptor(tool_name)
        wire_name = self._wire_name(tool_name)
        wire_kwargs = dict(kwargs)
        if connection is not None and "connection" not in wire_kwargs:
            wire_kwargs["connection"] = connection
        result = await self._client.call_tool(wire_name, wire_kwargs)
        value = self._structured_for_format(result)
        response = format_response(value, format_hint=descriptor.format_hint)
        return response.data

    @staticmethod
    def _structured_for_format(result: Any) -> Any:
        """Extract the formatter-friendly value from a CallToolResult.

        Prefers ``structured_content`` (raw dict / list shape that
        ``format_response`` consumes); unwraps FastMCP's
        ``{"result": [...]}`` list-wrap convention.
        """
        sc = getattr(result, "structured_content", None)
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        if sc is not None:
            return sc
        # Fall back to text content (e.g. plain-string tools).
        if hasattr(result, "content") and result.content:
            text = getattr(result.content[0], "text", None)
            if text is not None:
                return text
        return getattr(result, "data", None)

    async def invoke(
        self,
        tool_name: str,
        *,
        connection: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Invoke ``tool_name`` through the real MCP transport.

        Returns FastMCP's unmarshaled structured payload. See module
        docstring for the typed-return shape contract.
        """
        if self._client is None:
            raise RuntimeError("TestClient must be used as `async with client(app) as c:` before calling invoke().")
        wire_name = self._wire_name(tool_name)
        wire_kwargs = dict(kwargs)
        if connection is not None and "connection" not in wire_kwargs:
            wire_kwargs["connection"] = connection

        result = await self._client.call_tool(wire_name, wire_kwargs)
        return self._extract_payload(result)

    # --- internals ----------------------------------------------------- #

    @staticmethod
    def _extract_payload(result: Any) -> Any:
        if hasattr(result, "data") and result.data is not None:
            return result.data
        if hasattr(result, "structured_content") and result.structured_content is not None:
            return result.structured_content
        if hasattr(result, "content") and result.content:
            block = result.content[0]
            text = getattr(block, "text", None)
            if text is not None:
                import json as _json

                try:
                    return _json.loads(text)
                except _json.JSONDecodeError:
                    return text
        return result

    def _descriptor(self, tool_name: str) -> ToolDescriptor:
        for d in self.app.tools():
            if d.name == tool_name or _qualified(d) == tool_name:
                return d
        available = sorted(d.name for d in self.app.tools())
        raise KeyError(f"tool {tool_name!r} not found. Available: {available}")

    def _wire_name(self, tool_name: str) -> str:
        for d in self.app.tools():
            if d.name == tool_name or _qualified(d) == tool_name:
                m = d._meta  # noqa: SLF001 -- ToolDescriptor projection seam (privatize-tool-metadata)
                return m.tool_name if m is not None else d.name
        return tool_name


def _qualified(descriptor: ToolDescriptor) -> str:
    """Return ``<router-slug>.<tool-name>`` if the router has a slug."""
    slug = getattr(descriptor.router, "slug", None)
    return f"{slug}.{descriptor.name}" if slug else descriptor.name


def client(app: App) -> TestClient:
    """Construct a test client; use as ``async with client(app) as c: ...``."""
    return TestClient(app)


__all__ = ["TestClient", "client"]
