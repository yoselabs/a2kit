"""BDD — `serve --code-mode / --no-code-mode` is an absolute override pair.

The flag threads an `Optional[bool]` into `mcp_options["code_mode"]`:
`--code-mode` → True, `--no-code-mode` → False, neither → None (config decides).
The previous `--code-mode-off` spelling is gone. See change
`add-code-mode-config-default` (code-execution spec).
"""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import build_full_cli
from a2kit.testing import app_of


class _R(a2kit.Router):
    slug = "demo"

    @a2kit.read()
    async def echo(self) -> dict[str, str]:
        return {"msg": "ok"}


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Short-circuit `serve_process`, capturing the threaded `mcp_options`."""
    import a2kit.packages.serve as serve_mod

    box: dict[str, Any] = {}

    def _fake_serve_process(runtime: Any, **kwargs: Any) -> None:
        box["mcp_options"] = kwargs.get("mcp_options")

    monkeypatch.setattr(serve_mod, "serve_process", _fake_serve_process)
    return box


def _run(args: list[str]) -> Any:
    cli = build_full_cli(app_of("serve-flag-test", _R()))
    return CliRunner().invoke(cli, args)


def test_no_flag_threads_none(captured: dict[str, Any]) -> None:
    result = _run(["serve"])
    assert result.exit_code == 0, result.output
    assert captured["mcp_options"]["code_mode"] is None


def test_no_code_mode_forces_false(captured: dict[str, Any]) -> None:
    result = _run(["serve", "--no-code-mode"])
    assert result.exit_code == 0, result.output
    assert captured["mcp_options"]["code_mode"] is False


def test_code_mode_forces_true(captured: dict[str, Any]) -> None:
    result = _run(["serve", "--code-mode"])
    assert result.exit_code == 0, result.output
    assert captured["mcp_options"]["code_mode"] is True


def test_old_code_mode_off_spelling_is_gone(captured: dict[str, Any]) -> None:
    result = _run(["serve", "--code-mode-off"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
