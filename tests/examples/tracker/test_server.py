"""Tracker example — boot test through the connections plugin.

Saves a TrackerConn to a temp config dir via `A2KIT_CONFIG_HOME`, then calls
two tools end-to-end through the CLI. Catches v0.27 regressions in the
connections dispatch hook + container wiring (connection-as-plugin), and
verifies the `connection=` wire arg flows through to the resolved store.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def tracker_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("A2KIT_CONFIG_HOME", str(tmp_path / "connections"))

    # Reload the server module so its `install_connections(app, TrackerConn)`
    # call and `connections_cli(TrackerConn)` register against a fresh container under
    # the patched config home.
    import examples.tracker.connection as conn_mod
    import examples.tracker.routers as routers_mod
    import examples.tracker.store as store_mod
    import examples.tracker.server as srv

    importlib.reload(conn_mod)
    importlib.reload(store_mod)
    importlib.reload(routers_mod)
    importlib.reload(srv)

    # Persist a connection named "default" pointing at a temp JSONL.
    from a2kit.packages.connections.store import ConnectionStore

    db_path = tmp_path / "tracker.jsonl"
    store = ConnectionStore(conn_mod.TrackerConn)
    asyncio.run(store.save(conn_mod.TrackerConn(key=("default",), db_path=str(db_path))))

    from a2kit.packages.cli.builder import build_full_cli

    return build_full_cli(srv.app)


def test_create_and_list_project_through_connection(tracker_cli) -> None:
    runner = CliRunner()

    create = runner.invoke(
        tracker_cli,
        [
            "projects",
            "create_project",
            "--connection=default",
            "--name=Demo",
            "--format=json",
        ],
    )
    assert create.exit_code == 0, create.output
    created = json.loads(create.stdout.strip())
    assert created["name"] == "Demo"

    listed = runner.invoke(
        tracker_cli,
        ["projects", "list_projects", "--connection=default", "--format=json"],
    )
    assert listed.exit_code == 0, listed.output
    rows = json.loads(listed.stdout.strip())
    assert any(row["name"] == "Demo" for row in rows)


def test_missing_connection_surfaces_error(tracker_cli) -> None:
    """Calling a tool without --connection must fail (wire-required arg)."""
    runner = CliRunner()
    result = runner.invoke(
        tracker_cli,
        ["projects", "list_projects", "--format=json"],
        catch_exceptions=True,
    )
    assert result.exit_code != 0
    combined = (result.output or "") + (str(result.exception) if result.exception else "")
    assert "connection" in combined.lower()


# Reference os so a future `os.environ` introspection has the import — keeps
# the diff inert if someone later asserts on env state.
_ = os
