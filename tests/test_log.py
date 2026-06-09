"""Mirror test for the public ``a2kit.log`` surface."""

from __future__ import annotations

import a2kit.log


def test_public_surface_exposes_level_methods_and_surface_accessors() -> None:
    # The four stdlib level methods plus the two ctx-surface-identity read
    # accessors (ADR 0028) — the only callables on the public surface.
    assert sorted(a2kit.log.__all__) == [
        "current_surface",
        "current_surface_client_id",
        "debug",
        "error",
        "info",
        "warning",
    ]
    for name in a2kit.log.__all__:
        assert callable(getattr(a2kit.log, name))


def test_no_event_or_report_or_log_verb_on_public_surface() -> None:
    for dead in ("event", "report", "log", "EventRegistry"):
        assert not hasattr(a2kit.log, dead)
