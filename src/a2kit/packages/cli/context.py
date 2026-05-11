"""CLI ``fastmcp.Context``-shaped stub — emits compact LDD lines to stderr.

Mirrors the public surface of ``fastmcp.Context`` for tools that need to run
under either transport. Methods that are structurally MCP-only (sampling,
resource listing, prompt registries, notifications) raise
:class:`MCPOnlyError` with a clear pointer at the MCP transport.

All async signatures match ``fastmcp.Context`` so a tool written portably with
``await ctx.info(...)`` / ``await ctx.report_progress(...)`` works on both
transports.
"""

from __future__ import annotations

import sys
import time
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


class StderrToolContext:
    """CLI stub mimicking ``fastmcp.Context``'s public interface.

    Logging / progress / event / report methods render compact LDD lines to
    stderr. State (``set_state`` / ``get_state`` / ``delete_state``) lives in
    a per-instance dict. ``read_resource`` handles ``file://`` URIs only.
    ``elicit`` runs a primitive ``input()`` loop. Everything else raises
    :class:`MCPOnlyError`.

    The constructor's ``report_type`` / ``tool_name`` / ``reports_enabled`` /
    ``events_enabled`` kwargs are accepted for API compatibility — the
    runtime now sets these via :func:`a2kit.ldd.ldd_state_for_call` before
    each tool dispatch.
    """

    __slots__ = ("_start_ts", "_state")

    def __init__(
        self,
        *,
        report_type: type | None = None,  # noqa: ARG002 — accepted for API compatibility
        tool_name: str | None = None,  # noqa: ARG002
        reports_enabled: bool = True,  # noqa: ARG002
        events_enabled: bool = True,  # noqa: ARG002
    ) -> None:
        self._start_ts = time.monotonic()
        self._state: dict[str, Any] = {}

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

    async def read_resource(self, uri: str) -> Any:
        parsed = urlparse(str(uri))
        if parsed.scheme != "file":
            raise MCPOnlyError(
                "read_resource",
                hint=f"only file:// URIs are supported on CLI, got {parsed.scheme!r}",
            )
        path = Path(parsed.path)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_bytes()

    # --- Elicitation (primitive prompt loop) ------------------------------ #

    async def elicit(
        self,
        message: str,
        response_type: Any = None,
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

    # --- MCP-only surface (raise) ----------------------------------------- #

    async def sample(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        raise MCPOnlyError("sample", hint="LLM sampling needs an MCP client")

    async def sample_step(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ARG002
        raise MCPOnlyError("sample_step", hint="LLM sampling needs an MCP client")

    async def list_resources(self) -> Any:
        raise MCPOnlyError("list_resources")

    async def list_prompts(self) -> Any:
        raise MCPOnlyError("list_prompts")

    async def get_prompt(self, name: str, arguments: Any = None) -> Any:  # noqa: ARG002
        raise MCPOnlyError("get_prompt")

    async def list_roots(self) -> Any:
        raise MCPOnlyError("list_roots")

    async def send_notification(self, notification: Any) -> None:  # noqa: ARG002
        raise MCPOnlyError("send_notification")

    # --- Structured logger (matches MCP-side ``send_log_message``) -------- #

    async def send_log_message(
        self,
        level: str,
        logger: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit a structured log line: ``[ +s.mmm <LEVEL>] <logger> <kv>``.

        Mirrors the MCP-server-side ``send_log_message`` so portable code
        that wants structured fields (rather than ``info``'s free-form
        kwargs) renders identically on both transports. Coerces non-JSON
        values via ``str(v)`` to keep stderr legible.
        """
        label = _LEVEL_LABEL.get(level.lower(), level.upper())
        fields: dict[str, Any] = {}
        if data:
            for k, v in data.items():
                fields[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        msg = logger or ""
        self._emit(label, msg, fields)

    # --- LDD wire-format primitive (used by a2kit.ldd) -------------------- #

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
