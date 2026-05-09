"""Thin pytest fixtures for a2kit tests.

`cassette` is a vcrpy wrapper. `app` returns a fresh `a2kit.App`. There is
no DI-swap helper — tests construct routers with fake factories directly:

    app = a2kit.App("test")
    app.add_router(TasksRouter(fake_get_store))
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

import a2kit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@pytest.fixture
def cassette(tmp_path: Path) -> Callable[..., Any]:
    """Return a factory for vcrpy cassette context managers."""
    import vcr  # type: ignore[import-untyped]

    def _make(name: str, *, record_mode: str | None = None) -> Any:
        path = tmp_path / f"{name}.yaml"
        mode = record_mode if record_mode is not None else ("once" if not path.exists() else "none")
        return vcr.use_cassette(str(path), record_mode=mode)

    return _make


@pytest.fixture
def app() -> a2kit.App:
    """A fresh ``a2kit.App`` named ``"test"``."""
    return a2kit.App("test")


__all__ = ["app", "cassette"]
