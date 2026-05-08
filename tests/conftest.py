"""Shared fixtures: tmp_path config dirs, op-binary stubs, env scrubbing."""

from __future__ import annotations

# Opt into a2kit's pytest plugin for the schema_snapshot fixture.
pytest_plugins = ["a2kit.pytest_plugin"]

import os
import stat
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

import pytest

from a2kit import ConnectionConfig, ConnectionStore

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "connections"
    d.mkdir()
    return d


# -- Domain models used across tests -----------------------------------------


class DbKey(NamedTuple):
    project: str
    env: str
    db: str


class DbInfo(ConnectionConfig, key=DbKey):
    """Multi-field-key style record: 3-part key + DSN."""

    dsn: str


class AtlassianInfo(ConnectionConfig):
    """Flat-key style record: default `_DefaultKey(name)` + URL/email/token + read_only."""

    url: str
    email: str
    token: str
    read_only: bool = True


@pytest.fixture
def db_store(config_dir: Path) -> ConnectionStore[DbInfo]:
    return ConnectionStore(config_dir, DbInfo)


@pytest.fixture
def atlassian_store(config_dir: Path) -> ConnectionStore[AtlassianInfo]:
    return ConnectionStore(config_dir, AtlassianInfo)


# -- Fake `op` binary --------------------------------------------------------


@pytest.fixture
def fake_op_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Install a fake `op` shell script on PATH.

    Behaviour:
    - `op read op://vault/item/field` → prints "secret-from-op"
    - `op read op://fail/...` → exits 1 with stderr "session expired"
    - `op read op://timeout/...` → sleeps 30s (test must use small timeout)
    """
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
    # Also force a fresh PATH lookup per call by clearing shutil's cache (not used,
    # but defensive against any caching).
    yield script


@pytest.fixture
def no_op_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Replace PATH with an empty directory so `op` is not findable."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    # Keep the python interpreter dir so subprocess can still find shells if needed.
    py_dir = str(Path(sys.executable).parent)
    monkeypatch.setenv("PATH", f"{empty}{os.pathsep}{py_dir}")
