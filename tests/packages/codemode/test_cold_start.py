"""BDD: code-execution lazy-import + missing-runtime guard (code-execution-surface §7)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from a2kit.packages import codemode


def test_import_a2kit_does_not_pull_codemode_or_monty() -> None:
    """`import a2kit` must not import the Monty runtime or FastMCP `experimental` CodeMode."""
    probe = (
        "import sys, a2kit; "
        "bad = sorted(m for m in sys.modules "
        "if m == 'pydantic_monty' or 'experimental.transforms.code_mode' in m); "
        "assert not bad, bad"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_cli_startup_does_not_load_code_execution() -> None:
    """Building the CLI and running a non-`code` command imports nothing code-execution-related.

    Load-timing contract: in CLI mode the code-execution machinery
    (`a2kit.packages.codemode`, `fastmcp`, `pydantic-monty`) loads only
    when the `code` subcommand is invoked — never at CLI startup.
    """
    probe = """
import sys, a2kit
from a2kit.packages.cli.builder import build_full_cli
from click.testing import CliRunner


class R(a2kit.Router):
    slug = "x"

    @a2kit.read()
    async def ping(self) -> dict[str, bool]:
        return {"ok": True}

    tools = (ping,)


app = a2kit.AppBuilder("probe").add_router(R()).build()
cli = build_full_cli(app)
CliRunner().invoke(cli, ["--help"])
bad = sorted(
    m
    for m in sys.modules
    if m == "a2kit.packages.codemode" or m == "pydantic_monty" or m.startswith("fastmcp")
)
assert not bad, bad
"""
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_missing_monty_raises_with_migration_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """`build_code_mode_transform` fails fast with the `a2kit[code-mode]` hint."""
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str, package: str | None = None) -> object:
        if name == "pydantic_monty":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    with pytest.raises(ImportError, match=r"a2kit\[code-mode\]"):
        codemode.build_code_mode_transform()
