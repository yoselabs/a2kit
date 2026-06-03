"""Thin pytest fixtures for a2kit tests.

`cassette` is a vcrpy wrapper. `app` returns a fresh `a2kit.App`. There
is no DI-swap helper — tests construct routers with fake factories
directly and hand the App to a finisher:

    app = a2kit.App("test")
    app.add_router(TasksRouter(fake_get_store))

`ambient_for_tests` establishes an call scope so tests that call
orchestrator / phase functions directly (bypassing
``TestClient.invoke``) don't trip :class:`AmbientContextMissing`.
`ambient_for_tests_autouse` is the pre-decorated autouse peer for
consumers that want project-wide binding via a single import.

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
    from collections.abc import Callable, Iterator
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


def _ambient_for_tests_impl() -> Iterator[None]:
    """Wrap a test in a call scope so ``a2kit.log.*`` correlates by call_id.

    Tests that call orchestrator or phase functions directly (bypassing
    :func:`a2kit.testing.client`) run outside a dispatch, so emissions carry
    no ``call_id`` and no ``ctx`` for the wire. This fixture binds a
    :func:`a2kit.packages.log.scope.bind_call_scope` with a no-op
    :func:`a2kit.testing.null_context` so those code paths behave as if
    dispatched.

    Opt-in by design. Two adoption shapes are supported:

    - **Per-test opt-in** — declare ``ambient_for_tests`` in a test
      signature. The 5% case where some tests want ambient and others
      do not. Use this fixture.
    - **Project-wide binding** — import the pre-decorated peer
      :data:`ambient_for_tests_autouse` once in ``conftest.py``. The
      95% case. One-line import, no ``__wrapped__`` ceremony::

          # consumer's conftest.py
          from a2kit.testing import ambient_for_tests_autouse  # noqa: F401
    """
    from a2kit.packages.log import bind_call_scope
    from a2kit.packages.testing.null_context import null_context

    with bind_call_scope(ctx=null_context()):
        yield


# Decorate at module load only if pytest is importable. When pytest is not
# installed (production CLI on a non-dev venv), the names below stay as
# plain functions — ``import a2kit.packages.testing`` succeeds, just no
# fixtures get registered (which is fine, there's no pytest collector).
try:
    import pytest

    cassette = pytest.fixture(_cassette_impl)
    app = pytest.fixture(_app_impl)
    ambient_for_tests = pytest.fixture(_ambient_for_tests_impl)
    ambient_for_tests_autouse = pytest.fixture(autouse=True)(_ambient_for_tests_impl)
except ImportError:
    cassette = _cassette_impl  # type: ignore[assignment]
    app = _app_impl  # type: ignore[assignment]
    ambient_for_tests = _ambient_for_tests_impl  # type: ignore[assignment]
    ambient_for_tests_autouse = _ambient_for_tests_impl  # type: ignore[assignment]


__all__ = ["ambient_for_tests", "ambient_for_tests_autouse", "app", "cassette"]
