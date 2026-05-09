"""Local fixtures — isolated tmp config dirs, env scrubbing."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest

from a2kit.packages.connections import ConnectionConfig, ConnectionStore


class WidgetKey(NamedTuple):
    name: str


class WidgetConfig(ConnectionConfig, key=WidgetKey):
    token: str
    url: str = ""


class TripleKey(NamedTuple):
    project: str
    env: str
    db: str


class TripleConfig(ConnectionConfig, key=TripleKey):
    token: str
    region: str = "us-east"


@pytest.fixture
def cfg_dir(tmp_path: Path) -> Path:
    d = tmp_path / "connections"
    d.mkdir()
    return d


@pytest.fixture
def widget_store(cfg_dir: Path) -> ConnectionStore[WidgetConfig]:
    return ConnectionStore(WidgetConfig, cfg_dir)


@pytest.fixture
def triple_store(cfg_dir: Path) -> ConnectionStore[TripleConfig]:
    return ConnectionStore(TripleConfig, cfg_dir)


@pytest.fixture(autouse=True)
def _scrub_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("MY_TOKEN", "MISSING_VAR", "SOME_TOKEN"):
        monkeypatch.delenv(var, raising=False)
