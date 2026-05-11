"""Resource-pattern example — DI-aware lifecycle + lazy async resource open.

Boot test: catches v0.27 regressions at registration/startup time
(sync-only DI factories, typed-DI lifecycle handler signatures, non-Optional
state fields).
"""

from __future__ import annotations

import importlib
import json

from click.testing import CliRunner

from a2kit.packages.cli.builder import build_full_cli


def _fresh_app():
    """Reload the module so per-test the singleton AppState starts unopened."""
    import examples.resource_pattern.server as srv

    importlib.reload(srv)
    return srv.app


def test_tick_lazily_opens_resource_and_increments() -> None:
    cli = build_full_cli(_fresh_app())
    result = CliRunner().invoke(cli, ["fakeshop", "tick", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip())
    assert payload == {"count": 1, "history": []}


def test_tick_include_history_returns_per_call_history() -> None:
    cli = build_full_cli(_fresh_app())
    result = CliRunner().invoke(
        cli,
        ["fakeshop", "tick", "--include-history", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout.strip())
    assert payload == {"count": 1, "history": [1]}
