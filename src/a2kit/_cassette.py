"""HTTP cassette helper — thin wrapper around `vcrpy`.

Optional `[testing]` extra. The wrapper:

- Records HTTP traffic on first run; replays on subsequent runs.
- Plays nicely with both pytest functions and `async with` context-manager use.
- Honours the `--update-cassettes` pytest flag (registered by the pytest plugin).

Vcrpy's own integration story is fine; we ship a wrapper anyway because:

- The pytest plugin already owns one CLI flag (`--update-schema-snapshots`); a
  second is cheaper than asking consumers to wire their own.
- vcrpy's default `record_mode='once'` is the right default for our use case
  but is one configuration step every consumer would otherwise reinvent.

Public API: `cassette(path, *, record_mode=None)` returns a value that works as
both a function decorator and an async context manager.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


def _import_vcr() -> Any:
    try:
        import vcr  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:
        msg = "vcrpy is not installed; add `a2kit[testing]` to your dev deps."
        raise ImportError(msg) from exc
    return vcr


class _Cassette:
    """Hybrid decorator + context manager.

    Construction is lazy: the underlying `vcr.use_cassette()` is only called
    inside `_open()` so importing this module without vcrpy installed is fine,
    as long as you don't actually use the helper.
    """

    def __init__(self, path: str | Path, *, record_mode: str | None = None) -> None:
        self.path = Path(path)
        self.record_mode = record_mode

    def _resolved_record_mode(self) -> str:
        if self.record_mode is not None:
            return self.record_mode
        # File missing → record once. File present → replay only.
        return "once" if not self.path.exists() else "none"

    @contextmanager
    def _open(self) -> Iterator[Any]:
        vcr_module = _import_vcr()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with vcr_module.use_cassette(str(self.path), record_mode=self._resolved_record_mode()) as ctx:
            yield ctx

    # --- async context-manager protocol --------------------------------------

    async def __aenter__(self) -> Any:
        self._cm = self._open()
        return self._cm.__enter__()

    async def __aexit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)

    # --- sync context-manager protocol ---------------------------------------

    def __enter__(self) -> Any:
        self._cm = self._open()
        return self._cm.__enter__()

    def __exit__(self, *exc: object) -> None:
        self._cm.__exit__(*exc)

    # --- decorator -----------------------------------------------------------

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with self._open():
                return fn(*args, **kwargs)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with self._open():
                return await fn(*args, **kwargs)

        import inspect  # noqa: PLC0415 — keep import local

        return async_wrapper if inspect.iscoroutinefunction(fn) else sync_wrapper


def cassette(path: str | Path, *, record_mode: str | None = None) -> _Cassette:
    """Create a cassette helper. Use as decorator or `async with`."""
    return _Cassette(path, record_mode=record_mode)


__all__ = ["cassette"]
