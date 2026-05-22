"""Transport-neutral :class:`a2kit.ToolContext` implementations.

``StderrToolContext`` emits compact LDD lines to stderr. It is the
context used by the CLI transport and as the direct-call fallback on
the MCP dispatch path (a tool invoked outside a live FastMCP request).
Methods that are structurally MCP-only (sampling, resource listing,
prompt registries, notifications) raise :class:`MCPOnlyError` with a
clear pointer at the MCP transport.

The class structurally satisfies the ``a2kit.ToolContext`` Protocol; under the
MCP transport, ``fastmcp.Context`` satisfies the same Protocol. A tool written
portably with ``await ctx.info(...)`` / ``await ctx.report_progress(...)``
works on both.

This package is low-level: its only ``a2kit.packages.*`` dependency is a
lazy import of ``a2kit.packages.ldd`` (the ``format_ldd_line`` wire-format
primitive, inside ``_emit``). It imports no transport package, so it can
be shared by ``cli`` and ``mcp`` without a cycle.
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Mapping


class MCPOnlyError(RuntimeError):
    """Raised by the CLI stub for methods that have no CLI-side semantics."""

    def __init__(self, method: str, hint: str | None = None) -> None:
        self.method = method
        msg = f"ctx.{method}() requires MCP transport — no client-side facility available in CLI mode"
        if hint:
            msg += f" ({hint})"
        super().__init__(msg)


def _fields_with_logger(logger_name: str | None, extra: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compose `extra` into a flat fields dict, injecting `logger=...` if provided."""
    fields: dict[str, Any] = dict(extra) if extra else {}
    if logger_name:
        fields["logger"] = logger_name
    return fields


_LEVEL_LABEL: dict[str, str] = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARN",
    "error": "ERROR",
    "notice": "INFO",
    "critical": "ERROR",
    "alert": "ERROR",
    "emergency": "ERROR",
}


class _StubResourceResult:
    """Duck-typed stand-in for ``mcp.types.ResourceResult``.

    Exposes ``.content`` (the file's str or bytes). a2kit avoids
    importing the heavy ``mcp.types`` symbols on the cold-start
    path; consumers that need exact ``ResourceResult`` semantics
    use the real MCP transport.
    """

    __slots__ = ("content",)

    def __init__(self, *, content: str | bytes) -> None:
        self.content = content

    def __repr__(self) -> str:
        return f"_StubResourceResult(content={self.content!r})"


class StderrToolContext:
    """Implementation of :class:`a2kit.ToolContext` that emits to stderr.

    Logging / progress methods render compact LDD lines to stderr.
    State (``set_state`` / ``get_state`` / ``delete_state``) lives in
    a per-instance dict. ``read_resource`` handles ``file://`` URIs only.
    ``elicit`` runs a primitive ``input()`` loop. MCP-only methods raise
    :class:`MCPOnlyError`.

    ``request_id`` is a per-instance UUID4 (no wire-level request frame on
    CLI; the UUID is purely a correlation token for LDD lines). ``client_id``
    is ``None`` on CLI — there is no remote client.
    """

    __slots__ = ("_start_ts", "_state", "client_id", "request_id")

    def __init__(self) -> None:
        self._start_ts = time.monotonic()
        self._state: dict[str, Any] = {}
        self.request_id: str = uuid.uuid4().hex
        self.client_id: str | None = None

    # --- Logging (fastmcp.Context-shaped, all async) ---------------------- #
    #
    # Signatures match fastmcp.Context exactly: (message, logger_name=None,
    # extra=None). Field-bearing narrative logging lives on a2kit.ldd.* free
    # functions (info/warning/error/debug); they share `_emit` with these
    # methods so CLI rendering stays consistent. The kwargs-on-ctx pattern
    # crashed under MCP transport (fastmcp's narrow signature) — the divergence
    # is removed by routing fielded calls through a2kit.ldd.* instead.

    async def info(self, message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None) -> None:
        self._emit("INFO", message, _fields_with_logger(logger_name, extra))

    async def warning(self, message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None) -> None:
        self._emit("WARN", message, _fields_with_logger(logger_name, extra))

    async def error(self, message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None) -> None:
        self._emit("ERROR", message, _fields_with_logger(logger_name, extra))

    async def debug(self, message: str, logger_name: str | None = None, extra: Mapping[str, Any] | None = None) -> None:
        self._emit("DEBUG", message, _fields_with_logger(logger_name, extra))

    async def log(
        self,
        message: str,
        level: str | None = None,
        logger_name: str | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        label = _LEVEL_LABEL.get((level or "info").lower(), "INFO")
        fields: dict[str, Any] = {}
        if logger_name:
            fields["logger"] = logger_name
        if extra:
            fields.update(extra)
        self._emit(label, message, fields)

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        fields: dict[str, Any] = {"current": progress, "total": total}
        if message:
            fields["message"] = message
        self._emit("progress", "", fields)

    # --- State (per-instance dict) ---------------------------------------- #

    async def set_state(self, key: str, value: Any, *, serializable: bool = True) -> None:  # noqa: ARG002
        self._state[key] = value

    async def get_state(self, key: str) -> Any:
        return self._state.get(key)

    async def delete_state(self, key: str) -> None:
        self._state.pop(key, None)

    # --- Resources (file:// only on CLI) ---------------------------------- #

    async def read_resource(self, uri: str | Any) -> Any:
        """Read a file:// resource and return a fastmcp-shaped result.

        Signature mirrors ``fastmcp.Context.read_resource(uri: str | AnyUrl)
        -> ResourceResult``. The return type is duck-typed
        (``_StubResourceResult``) to avoid an eager ``mcp.types`` import on
        cold-start; it exposes the ``.content`` attribute consumers
        expect.

        ``AnyUrl`` is accepted via ``str(uri)`` coercion; the runtime type
        annotation stays loose to avoid importing pydantic.AnyUrl on
        every CLI invocation.
        """
        parsed = urlparse(str(uri))
        if parsed.scheme != "file":
            raise MCPOnlyError(
                "read_resource",
                hint=f"only file:// URIs are supported on CLI, got {parsed.scheme!r}",
            )
        path = Path(parsed.path)
        try:
            content: str | bytes = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_bytes()
        return _StubResourceResult(content=content)

    # --- Elicitation (primitive prompt loop) ------------------------------ #

    async def elicit(
        self,
        message: str,
        response_type: type[Any] | list[str] | dict[str, dict[str, str]] | list[list[str]] | list[dict[str, dict[str, str]]] | None = None,
        *,
        response_title: str | None = None,  # noqa: ARG002
        response_description: str | None = None,  # noqa: ARG002
    ) -> Any:
        from fastmcp.server.elicitation import (
            AcceptedElicitation,
            CancelledElicitation,
            DeclinedElicitation,
        )

        # Write the prompt to stderr (not stdout) so the tool's JSON return
        # value on stdout stays parseable. Then read a single line via input().
        sys.stderr.write(f"{message}\n> ")
        sys.stderr.flush()
        try:
            raw = input()
        except EOFError:
            return CancelledElicitation()
        except KeyboardInterrupt:
            return CancelledElicitation()

        if raw.strip() == "--decline":
            return DeclinedElicitation()

        value = self._coerce_elicit_value(raw, response_type)
        return AcceptedElicitation(data=value)

    @staticmethod
    def _coerce_elicit_value(raw: str, response_type: Any) -> Any:
        if response_type is None or response_type is str:
            return raw
        if response_type is int:
            return int(raw)
        if response_type is float:
            return float(raw)
        if response_type is bool:
            return raw.strip().lower() in {"1", "true", "yes", "y"}
        if isinstance(response_type, list):
            if raw not in response_type:
                raise MCPOnlyError(
                    "elicit",
                    hint=f"value {raw!r} not in enum options {response_type!r}",
                )
            return raw
        raise MCPOnlyError(
            "elicit",
            hint=f"complex/nested response_type {response_type!r} not supported on CLI — use MCP transport",
        )

    # --- MCP-only surface (signature-mirror-then-raise) ------------------- #
    #
    # Signatures match ``fastmcp.Context`` exactly (per
    # ``align-context-method-signatures`` Treatment 2). Bodies are a
    # single ``raise MCPOnlyError(...)``. The signature parity is
    # asserted by ``test_stub_signature_matches_fastmcp`` so any
    # upstream fastmcp drift surfaces at CI time.
    #
    # Parameter types use string-quoted forms or ``Any`` to keep the
    # cold-start path light — these signatures must not eagerly import
    # ``mcp.types``, ``fastmcp.server.sampling.*``, etc., on a bare
    # ``import a2kit``.

    async def sample(
        self,
        messages: Any,  # noqa: ARG002
        *,
        system_prompt: str | None = None,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        max_tokens: int | None = None,  # noqa: ARG002
        model_preferences: Any = None,  # noqa: ARG002
        tools: Any = None,  # noqa: ARG002
        result_type: Any = None,  # noqa: ARG002
        mask_error_details: bool | None = None,  # noqa: ARG002
        tool_concurrency: int | None = None,  # noqa: ARG002
    ) -> Any:
        raise MCPOnlyError("sample", hint="LLM sampling needs an MCP client")

    async def sample_step(
        self,
        messages: Any,  # noqa: ARG002
        *,
        system_prompt: str | None = None,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        max_tokens: int | None = None,  # noqa: ARG002
        model_preferences: Any = None,  # noqa: ARG002
        tools: Any = None,  # noqa: ARG002
        tool_choice: Any = None,  # noqa: ARG002
        execute_tools: bool = True,  # noqa: ARG002
        mask_error_details: bool | None = None,  # noqa: ARG002
        tool_concurrency: int | None = None,  # noqa: ARG002
    ) -> Any:
        raise MCPOnlyError("sample_step", hint="LLM sampling needs an MCP client")

    async def list_resources(self) -> Any:
        raise MCPOnlyError("list_resources")

    async def list_prompts(self) -> Any:
        raise MCPOnlyError("list_prompts")

    async def get_prompt(
        self,
        name: str,  # noqa: ARG002
        arguments: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> Any:
        raise MCPOnlyError("get_prompt")

    async def list_roots(self) -> Any:
        raise MCPOnlyError("list_roots")

    async def send_notification(self, notification: Any) -> None:  # noqa: ARG002
        raise MCPOnlyError("send_notification")

    # --- LDD wire-format primitive (used by a2kit.ldd) -------------------- #
    # (Note: previously ``send_log_message`` mirrored the MCP-side
    # session method here, but it was never invoked from anywhere in
    # src/, tests/, or examples/ — deleted per
    # ``align-context-method-signatures`` Treatment 3. ``a2kit.ldd``
    # routes directly through ``_emit`` on the CLI side.)

    def _emit(
        self,
        level: str,
        msg: str,
        fields: Mapping[str, Any],
        *,
        elapsed_ms: int | None = None,
    ) -> None:
        from a2kit.packages.ldd import format_ldd_line

        if elapsed_ms is None:
            elapsed_ms = round((time.monotonic() - self._start_ts) * 1000)
        line = format_ldd_line(level, msg, fields, elapsed_ms)
        print(line, file=sys.stderr, flush=True)  # noqa: T201


__all__ = ["MCPOnlyError", "StderrToolContext"]
