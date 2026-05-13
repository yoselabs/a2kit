"""Thin pytest fixtures for a2kit tests.

`cassette` is a vcrpy wrapper. `app` returns a fresh `a2kit.App`. There is
no DI-swap helper — tests construct routers with fake factories directly:

    app = a2kit.App("test")
    app.add_router(TasksRouter(fake_get_store))

v0.33: ``pytest`` is imported lazily inside the fixture bodies so that
``import a2kit.packages.testing`` does not require pytest at import time.
Production CLI subcommands (notably ``<app> health``) decouple from this
package anyway (see ``a2kit.packages.cli.builder._register_health``), but
keeping pytest off the import path is defense in depth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import a2kit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _cassette_impl(tmp_path: Path) -> Callable[..., Any]:
    """Return a factory for vcrpy cassette context managers."""
    import vcr  # type: ignore[import-untyped]

    def _make(name: str, *, record_mode: str | None = None) -> Any:
        path = tmp_path / f"{name}.yaml"
        mode = record_mode if record_mode is not None else ("once" if not path.exists() else "none")
        return vcr.use_cassette(str(path), record_mode=mode)

    return _make


def _app_impl() -> a2kit.App:
    """A fresh ``a2kit.App`` named ``"test"``."""
    return a2kit.App("test")


# Decorate at module load only if pytest is importable. When pytest is not
# installed (production CLI on a non-dev venv), the names below stay as
# plain functions — ``import a2kit.packages.testing`` succeeds, just no
# fixtures get registered (which is fine, there's no pytest collector).
try:
    import pytest

    cassette = pytest.fixture(_cassette_impl)
    app = pytest.fixture(_app_impl)
except ImportError:
    cassette = _cassette_impl  # type: ignore[assignment]
    app = _app_impl  # type: ignore[assignment]


__all__ = ["app", "cassette"]
