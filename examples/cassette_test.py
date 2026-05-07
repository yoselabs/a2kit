"""Example: `a2kit.testing.cassette` — record/replay HTTP traffic.

Demonstrates the helper without an actual network call (we patch `vcr` so the
example is hermetic). In a real test you'd issue HTTPS requests inside the
context manager and the cassette YAML would record/replay them.

Run: `uv run python examples/cassette_test.py`
"""

from __future__ import annotations

import builtins
import tempfile
from pathlib import Path
from typing import Any


class _FakeCtx:
    def __enter__(self) -> _FakeCtx:
        print("[vcr] cassette opened")
        return self

    def __exit__(self, *exc: object) -> None:
        print("[vcr] cassette closed")


class _FakeVcr:
    def use_cassette(self, path: str, record_mode: str | None = None) -> _FakeCtx:
        print(f"[vcr] use_cassette path={path} mode={record_mode}")
        return _FakeCtx()


def main() -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "vcr":
            return _FakeVcr()
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        import a2kit

        path = Path(tempfile.mkdtemp()) / "demo.yaml"

        @a2kit.testing.cassette(path)
        def make_request() -> str:
            print("(would issue HTTP request here)")
            return "ok"

        print("first call (cassette absent → record mode 'once'):")
        print("  result:", make_request())
        path.write_text("placeholder")
        print("\nsecond call (cassette present → record mode 'none' / replay):")
        print("  result:", make_request())
    finally:
        builtins.__import__ = real_import


if __name__ == "__main__":
    main()
