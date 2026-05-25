from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Eagerly load the bundled surface packages so their Surface instances
# self-register with the dispatch registry (and the kernel name registry)
# before any test imports a2kit and decorates a tool. With
# `surface-set-from-registry` shipped, `@a2kit.read(expose=("mcp","api"))`
# validates against the live registry; tests that decorate without first
# importing these packages would hit an empty-registry error.
import a2kit.packages.http  # noqa: F401, E402
import a2kit.packages.mcp  # noqa: F401, E402

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
