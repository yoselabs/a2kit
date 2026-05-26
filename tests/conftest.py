from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Per `bootstrap-surfaces-explicit` (2026-05-26), surfaces are no longer
# self-registered as import side effects. Compose the default surface set
# (mcp + api) once at conftest import so every test sees a populated
# registry. Tests that exercise `runtime.build(app)` directly inherit the
# bound registry via the deprecation-shim proxy; tests that exercise
# `runtime.build(app, surfaces=registry)` pass it explicitly.
import a2kit as _a2kit  # noqa: E402

_a2kit.compose_default_surfaces()

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "connections"
    d.mkdir()
    return d


@pytest.fixture
def fake_op_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "op"
    script.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$2" == op://fail/* ]]; then echo "session expired" >&2; exit 1; fi\n'
        'if [[ "$2" == op://timeout/* ]]; then sleep 30; fi\n'
        'echo "secret-from-op"\n'
    )
    script.chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    yield script


@pytest.fixture
def no_op_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty-path"
    empty.mkdir()
    py_dir = str(Path(sys.executable).parent)
    monkeypatch.setenv("PATH", f"{empty}{os.pathsep}{py_dir}")
