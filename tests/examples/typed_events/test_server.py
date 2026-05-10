"""Typed-events example — CLI emits StepStarted/StepCompleted with progress."""

from __future__ import annotations

import json

from click.testing import CliRunner

from a2kit.packages.cli.builder import build_full_cli
from examples.typed_events.server import app


def test_typed_events_emit_to_stderr_with_progress() -> None:
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["jobs", "run", "--steps", "2"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload == {"steps": 2}
    err = result.stderr
    # Each typed event renders as a structured event line + a progress line.
    assert "StepStarted" in err
    assert "StepCompleted" in err
    assert "step=1" in err
    assert "step=2" in err
    assert "current=1" in err
    assert "current=2" in err
