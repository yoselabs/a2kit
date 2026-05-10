"""Health-demo example — CLI `health` shorthand + lifecycle-gated probe."""

from __future__ import annotations

import json

from click.testing import CliRunner

from a2kit.packages.cli.builder import build_full_cli


def test_health_shorthand_runs_lifecycle_then_passes() -> None:
    """`<app> health` runs the App's lifecycle so `_sqlite_open` flips to ok."""
    # Re-import inside the test so the module's `_state.sqlite_open` starts False.
    import importlib

    import examples.health_demo.server as srv

    importlib.reload(srv)

    cli = build_full_cli(srv.app)
    result = CliRunner().invoke(cli, ["health"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    statuses = {c["name"]: c["status"] for c in payload["checks"]}
    assert statuses == {"_ping": "ok", "_sqlite_open": "ok"}
