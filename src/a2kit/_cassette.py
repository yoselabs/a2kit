"""HTTP cassette helper — thin pass-through to `vcrpy`.

The kit's contribution is a 5-line policy: missing cassette → record once;
existing cassette → replay only. Otherwise this is `vcr.use_cassette(...)`
unchanged.

vcrpy's returned object (`CassetteContextDecorator`) already supports both
sync context-manager use (`with cassette(...): ...`) and decorator use
(`@cassette(...)`). v0.13 dropped the bespoke async-CM adapter — vcrpy
records HTTP synchronously at the socket layer, so `async with` was never
doing anything async-aware.

vcrpy ships in the optional `a2kit[testing]` extra; this module imports it
lazily so a minimal install can still import `a2kit.testing`.

Public API: `cassette(path, *, record_mode=None) -> CassetteContextDecorator`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _import_vcr() -> Any:
    try:
        import vcr  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError as exc:
        msg = "vcrpy is not installed; add `a2kit[testing]` to your dev deps."
        raise ImportError(msg) from exc
    return vcr


def cassette(path: str | Path, *, record_mode: str | None = None) -> Any:
    """Return a vcrpy cassette CM/decorator with kit-friendly defaults.

    `record_mode` defaults to `"once"` when the cassette file is missing
    (record on first run) and `"none"` when present (replay only). Pass an
    explicit value to override.
    """
    vcr = _import_vcr()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = record_mode if record_mode is not None else ("once" if not p.exists() else "none")
    return vcr.use_cassette(str(p), record_mode=mode)


__all__ = ["cassette"]
