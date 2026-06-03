"""Mirror unit tests for ``a2kit._log_bootstrap``."""

from __future__ import annotations

import logging

from a2kit._log_bootstrap import configure_logging
from a2kit.config import LogConfig


def _managed_handlers(name: str) -> list[logging.Handler]:
    return [h for h in logging.getLogger(name).handlers if getattr(h, "_a2kit_managed", False)]


def test_default_config_installs_filter_no_streaming_handlers() -> None:
    configure_logging(LogConfig())
    a2kit = logging.getLogger("a2kit")
    assert any(getattr(f, "_a2kit_managed", False) for f in a2kit.filters)
    # stderr_sink defaults to "none" → no managed streaming handler.
    assert _managed_handlers("a2kit") == []


def test_is_idempotent_across_calls() -> None:
    configure_logging(LogConfig(stderr_sink="pretty"))
    first = len(_managed_handlers("a2kit"))
    configure_logging(LogConfig(stderr_sink="pretty"))
    second = len(_managed_handlers("a2kit"))
    assert first == second == 1


def test_disabled_sets_drop_everything_level() -> None:
    configure_logging(LogConfig(enabled=False))
    assert logging.getLogger("a2kit").level > logging.CRITICAL
    configure_logging(LogConfig())  # restore for other tests


def test_call_log_on_wires_dedicated_non_streaming_logger(tmp_path: object) -> None:
    configure_logging(LogConfig(call_log="on", call_log_dir=str(tmp_path)))
    calls = logging.getLogger("a2kit.calls")
    assert calls.propagate is False
    assert len(_managed_handlers("a2kit.calls")) == 1
    configure_logging(LogConfig())  # restore
