"""Mirror unit tests for ``a2kit.packages.log.handlers``."""

from __future__ import annotations

import logging

import pytest

from a2kit.packages.log.handlers import StderrJsonHandler, StderrPrettyHandler, _IsolatingHandler


def _record(msg: str = "hello", fields: dict | None = None, level: int = logging.INFO) -> logging.LogRecord:
    rec = logging.LogRecord("a2kit", level, __file__, 0, msg, None, None)
    rec.a2kit_fields = fields or {}
    rec.elapsed_ms = 0
    return rec


def test_stderr_pretty_writes_condensed_line(capsys: pytest.CaptureFixture[str]) -> None:
    StderrPrettyHandler().emit(_record("starting", {"host": "x.com"}))
    err = capsys.readouterr().err
    assert "INFO    ] starting" in err
    assert "host='x.com'" in err


def test_stderr_json_writes_one_json_object(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    StderrJsonHandler().emit(_record("boom", {"k": 1}, level=logging.ERROR))
    err = capsys.readouterr().err.strip()
    row = json.loads(err)
    assert row["level"] == "ERROR"
    assert row["msg"] == "boom"
    assert row["fields"] == {"k": 1}


def test_failing_handler_is_isolated_not_raised() -> None:
    class _Boom(_IsolatingHandler):
        def _safe_emit(self, record: logging.LogRecord) -> None:
            raise RuntimeError("kaboom")

    # Must NOT raise — isolation is the contract.
    _Boom().emit(_record())
