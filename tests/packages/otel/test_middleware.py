"""Span / metric assertions against ``OTelMiddleware`` using OTel SDK in-memory exporters."""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import a2kit
from a2kit.packages.mcp import build_mcp_server
from a2kit.packages.otel import OTelMiddleware


# OTel global providers can only be set once per process. Wire them up
# at module-import time, but hand each test fresh in-memory exporters by
# clearing them between runs.
_SPAN_EXPORTER = InMemorySpanExporter()
_METRIC_READER = InMemoryMetricReader()
_TRACER_PROVIDER = TracerProvider()
_TRACER_PROVIDER.add_span_processor(SimpleSpanProcessor(_SPAN_EXPORTER))
_METER_PROVIDER = MeterProvider(metric_readers=[_METRIC_READER])

# Set globals once. Subsequent ``set_*_provider`` calls become no-ops, so
# fixtures can re-clear in-memory state without re-installing providers.
from opentelemetry import metrics as _metrics  # noqa: E402, I001
from opentelemetry import trace as _trace  # noqa: E402

_trace.set_tracer_provider(_TRACER_PROVIDER)
_metrics.set_meter_provider(_METER_PROVIDER)


@pytest.fixture
def tracing() -> tuple[InMemorySpanExporter, InMemoryMetricReader]:
    """Hand the in-memory exporter / reader to a test, cleared of prior data."""
    _SPAN_EXPORTER.clear()
    # Drain any metrics accumulated by earlier tests.
    _METRIC_READER.get_metrics_data()
    return _SPAN_EXPORTER, _METRIC_READER


class _FakeMessage:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeFastMCPCtx:
    def __init__(self, server: Any, request_id: str = "req-42") -> None:
        self.fastmcp = server
        self.request_id = request_id


class _FakeMiddlewareContext:
    def __init__(self, name: str, server: Any) -> None:
        self.message = _FakeMessage(name)
        self.fastmcp_context = _FakeFastMCPCtx(server)


def _build_server() -> Any:
    class _R(a2kit.Router):
        slug = "things"
        name = "things"

        @a2kit.read()
        async def ping(self) -> dict[str, int]:
            return {"x": 1}

        @a2kit.write()
        async def boom(self) -> dict[str, int]:
            raise RuntimeError("kaboom")

        tools = (
            ping,
            boom,
        )

    app = a2kit.App("demo-app").add_router(_R())
    return build_mcp_server(app)


async def _ok_call_next(_ctx: Any) -> dict[str, str]:
    return {"ok": True}


async def _fail_call_next(_ctx: Any) -> dict[str, str]:
    raise RuntimeError("kaboom")


@pytest.mark.asyncio
async def test_span_emitted_on_success(tracing: Any) -> None:
    span_exporter, _metric_reader = tracing
    server = _build_server()
    mw = OTelMiddleware()

    fake_ctx = _FakeMiddlewareContext("ping", server)
    result = await mw.on_call_tool(fake_ctx, _ok_call_next)
    assert result == {"ok": True}

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "mcp.tool.ping"
    attrs = dict(span.attributes or {})
    assert attrs["a2kit.tool_name"] == "ping"
    assert attrs["a2kit.verb"] == "read"
    assert attrs["a2kit.router"] == "things"
    # framework auto-stamps the verb tag
    assert "read" in attrs["a2kit.tags"]
    assert attrs["mcp.request_id"] == "req-42"
    # OK status
    assert span.status.status_code.name == "OK"


@pytest.mark.asyncio
async def test_span_records_exception_on_error(tracing: Any) -> None:
    span_exporter, _metric_reader = tracing
    server = _build_server()
    mw = OTelMiddleware()

    fake_ctx = _FakeMiddlewareContext("boom", server)
    with pytest.raises(RuntimeError, match="kaboom"):
        await mw.on_call_tool(fake_ctx, _fail_call_next)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "mcp.tool.boom"
    assert span.status.status_code.name == "ERROR"
    # Recorded exception event.
    event_names = [e.name for e in span.events]
    assert "exception" in event_names


@pytest.mark.asyncio
async def test_counter_increments_with_status(tracing: Any) -> None:
    _span_exporter, metric_reader = tracing
    server = _build_server()
    mw = OTelMiddleware()

    await mw.on_call_tool(_FakeMiddlewareContext("ping", server), _ok_call_next)
    with pytest.raises(RuntimeError):
        await mw.on_call_tool(_FakeMiddlewareContext("boom", server), _fail_call_next)

    data = metric_reader.get_metrics_data()
    assert data is not None
    points: list[Any] = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == "a2kit.tool.calls":
                    points.extend(metric.data.data_points)

    statuses = sorted((p.attributes.get("status"), p.attributes.get("tool")) for p in points)
    assert ("error", "boom") in statuses
    assert ("ok", "ping") in statuses


@pytest.mark.asyncio
async def test_unknown_tool_still_emits_span(tracing: Any) -> None:
    """No matching tool in the registry → span still records what we know."""
    span_exporter, _metric_reader = tracing
    server = _build_server()
    mw = OTelMiddleware()

    await mw.on_call_tool(_FakeMiddlewareContext("nonexistent", server), _ok_call_next)
    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert attrs["a2kit.tool_name"] == "nonexistent"
    # No verb / router / tags when meta is missing — keys absent.
    assert "a2kit.verb" not in attrs
    assert "a2kit.router" not in attrs
