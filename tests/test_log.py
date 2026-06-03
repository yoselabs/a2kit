"""Mirror test for the public ``a2kit.log`` surface."""

from __future__ import annotations

import a2kit.log


def test_public_surface_exposes_only_level_methods() -> None:
    assert sorted(a2kit.log.__all__) == ["debug", "error", "info", "warning"]
    for name in a2kit.log.__all__:
        assert callable(getattr(a2kit.log, name))


def test_no_event_or_report_or_log_verb_on_public_surface() -> None:
    for dead in ("event", "report", "log", "EventRegistry"):
        assert not hasattr(a2kit.log, dead)
