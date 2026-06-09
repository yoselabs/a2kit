"""The call access-log — the durable, queryable record of every tool call.

Two pieces live here:

- :class:`CallRecord` — the span-shaped record the dispatch-boundary stage
  produces (``call_id`` + span fields + captured args/result/timing/principal).
  Span-shaped on the OpenTelemetry *data model* — NOT the SDK (its cold-start
  cost is rejected on the same ADR-0020 grounds as structlog).
- :class:`CallLogFileHandler` — a stdlib ``logging.Handler`` that persists
  records as one JSON object per line (jsonl, DuckDB-queryable), with large
  string bodies content-addressed to ``bodies/<hash>`` sidecars so domain
  scans read thin rows and touch a blob only when opened. Newlines inside any
  value are JSON-escaped, so every record stays one physical line.

The handler is attached ONLY to the dedicated ``a2kit.calls`` logger
(``propagate=False``) — never to the streaming handlers — so call records
structurally cannot reach the agent wire or stdout.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Columns kept in the thin jsonl row, in stable order. Body-ish fields
# (``args`` / ``result``) follow; large string values among them are
# content-addressed out to sidecars.
_SPAN_COLUMNS = ("call_id", "ts", "tool", "surface", "domain", "principal", "elapsed_ms", "trace_id", "span_id", "parent_span_id")


@dataclass
class CallRecord:
    """One structured record per tool call — produced at the dispatch boundary."""

    call_id: str
    tool: str | None = None
    #: The dispatching surface (``"mcp"`` | ``"api"`` | ``"cli"``), or None
    #: (ctx-surface-identity, ADR 0028).
    surface: str | None = None
    domain: str | None = None
    principal: str | None = None
    elapsed_ms: int | None = None
    args: dict[str, Any] = field(default_factory=dict)  # noqa: AK214 -- captured tool args are free-form by design
    result: Any = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    ts: float | None = None

    def to_row(self) -> dict[str, Any]:  # noqa: AK214 -- jsonl row is free-form by design
        """Flatten to an ordered jsonl row dict (bodies not yet sidecar'd)."""
        row: dict[str, Any] = {col: getattr(self, col) for col in _SPAN_COLUMNS}
        row["args"] = self.args
        row["result"] = self.result
        return row


def _content_address(row: dict[str, Any], bodies_dir: Path, inline_threshold: int) -> dict[str, Any]:
    """Replace each large top-level string value with a ``<key>_hash`` pointer.

    The body is written to ``bodies/<sha256>`` (content-addressed, so identical
    bodies dedupe). Small values and non-strings stay inline.
    """
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and len(value) > inline_threshold:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            bodies_dir.mkdir(parents=True, exist_ok=True)
            sidecar = bodies_dir / digest
            if not sidecar.exists():
                sidecar.write_text(value, encoding="utf-8")
            out[f"{key}_hash"] = digest
        else:
            out[key] = value
    return out


class CallLogFileHandler(logging.Handler):
    """Persist call records (and correlated debug rows) as queryable jsonl.

    Sync by design: a file write already means "write now", so this is a plain
    synchronous handler (unlike the MCP wire, which must stay async-inline).
    """

    def __init__(self, *, log_dir: Path | str, inline_threshold: int = 4096) -> None:
        super().__init__()
        self._dir = Path(log_dir)
        self._inline_threshold = inline_threshold

    def _row_for(self, record: logging.LogRecord) -> dict[str, Any]:
        call_record: CallRecord | None = getattr(record, "a2kit_call_record", None)
        if call_record is not None:
            row = call_record.to_row()
            if row.get("ts") is None:
                row["ts"] = record.created
            return row
        # Correlated debug/enrichment row from the a2kit logger: keep the
        # call_id spine + the structured fields so a DuckDB GROUP BY call_id
        # reconstructs the full call.
        return {
            "call_id": getattr(record, "call_id", None),
            "ts": record.created,
            "tool": getattr(record, "tool_name", None),
            "level": record.levelname,
            "msg": record.getMessage(),
            "elapsed_ms": getattr(record, "elapsed_ms", None),
            **getattr(record, "a2kit_fields", {}),
        }

    def emit(self, record: logging.LogRecord) -> None:
        try:
            row = self._row_for(record)
            row = _content_address(row, self._dir / "bodies", self._inline_threshold)
            day = time.strftime("%Y-%m-%d", time.gmtime(row.get("ts") or record.created))
            calls_dir = self._dir / "calls"
            calls_dir.mkdir(parents=True, exist_ok=True)
            line = json.dumps(row, default=str, ensure_ascii=False)
            with (calls_dir / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001 -- a logging handler must never abort its producer
            self.handleError(record)
