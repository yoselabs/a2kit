"""Tests for new v1.0 lint rules: A2K-DI-*, A2K-CONN-LIST-PLACEHOLDER, A2K-IMPORT-DISCIPLINE."""

from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from a2kit.packages.lint.cli import main as cli_main
from a2kit.packages.lint.static import (
    A2K_CONN_LIST_PLACEHOLDER,
    A2K_DI_ANNOTATED,
    A2K_DI_IMPORT_LEGACY,
    A2K_DI_IMPORT_SLOW,
    A2K_DI_KWONLY,
    A2K_DI_PYDANTIC_VALIDATE,
    A2K_IMPORT_DISCIPLINE,
    run_static_rules,
)


def _write(tmp_path: Path, name: str, body: str, *, subdir: str = "src") -> Path:
    d = tmp_path / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- A2K-DI-ANNOTATED --------------------------- #


def test_di_annotated_fires_on_annotated_depends(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from typing import Annotated\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db: Annotated[int, Depends(get_db)]) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED in _codes(findings)


def test_di_annotated_silent_on_default_form(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db: int = Depends(get_db)) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_ANNOTATED not in _codes(findings)


# --------------------------- A2K-DI-IMPORT-LEGACY --------------------------- #


def test_di_import_legacy_fires(tmp_path: Path) -> None:
    body = "from a2kit.di import Depends\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_LEGACY in _codes(findings)


def test_di_import_legacy_silent_on_uncalled_for(tmp_path: Path) -> None:
    body = "from uncalled_for import Depends\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_LEGACY not in _codes(findings)


# --------------------------- A2K-DI-IMPORT-SLOW --------------------------- #


def test_di_import_slow_fires(tmp_path: Path) -> None:
    body = "from fastmcp.dependencies import Depends\n"
    # Use packages/mcp allowlisted path so A2K-IMPORT-DISCIPLINE doesn't also fire.
    p = _write(tmp_path, "m.py", body, subdir="src/a2kit/packages/mcp")
    findings = run_static_rules([p])
    assert A2K_DI_IMPORT_SLOW in _codes(findings)


# --------------------------- A2K-DI-KWONLY --------------------------- #


def test_di_kwonly_fires_on_positional_depends(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(db = Depends(get_db)) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY in _codes(findings)


def test_di_kwonly_silent_when_kwonly(tmp_path: Path) -> None:
    body = (
        "import a2kit\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "@a2kit.tool()\n"
        "def t(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_KWONLY not in _codes(findings)


# --------------------------- A2K-DI-PYDANTIC-VALIDATE --------------------------- #


def test_di_pydantic_validate_fires_on_depends_fn(tmp_path: Path) -> None:
    body = (
        "import pydantic\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = pydantic.validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE in _codes(findings)


def test_di_pydantic_validate_silent_on_clean_fn(tmp_path: Path) -> None:
    body = "import pydantic\ndef fn(x: int) -> int:\n    return x\nwrapped = pydantic.validate_call(fn)\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE not in _codes(findings)


def test_di_pydantic_validate_bare_import(tmp_path: Path) -> None:
    body = (
        "from pydantic import validate_call\n"
        "from uncalled_for import Depends\n"
        "def get_db(): ...\n"
        "def fn(*, db = Depends(get_db)) -> int:\n"
        "    return 1\n"
        "wrapped = validate_call(fn)\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_DI_PYDANTIC_VALIDATE in _codes(findings)


# --------------------------- A2K-CONN-LIST-PLACEHOLDER --------------------------- #


def test_conn_list_placeholder_fires_on_list(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    tags: list = ['${MY_TAG}', 'plain']\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_fires_on_dict(tmp_path: Path) -> None:
    body = "from a2kit.connections import ConnectionConfig\nclass C(ConnectionConfig):\n    headers: dict = {'auth': '${TOKEN}'}\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER in _codes(findings)


def test_conn_list_placeholder_silent_on_scalar(tmp_path: Path) -> None:
    body = (
        "from a2kit.connections import ConnectionConfig\n"
        "class C(ConnectionConfig):\n"
        "    token: str = '${TOKEN}'\n"  # scalar — out of scope; ${} substitution works
        "    tags: list = ['plain', 'simple']\n"
    )
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


def test_conn_list_placeholder_silent_on_non_connection_class(tmp_path: Path) -> None:
    body = "from pydantic import BaseModel\nclass C(BaseModel):\n    tags: list = ['${MY_TAG}']\n"
    p = _write(tmp_path, "m.py", body)
    findings = run_static_rules([p])
    assert A2K_CONN_LIST_PLACEHOLDER not in _codes(findings)


# --------------------------- A2K-IMPORT-DISCIPLINE --------------------------- #


def test_import_discipline_fires_outside_allowlist(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    # Mimic a forbidden path.
    p = _write(tmp_path, "m.py", body, subdir="src/a2kit/packages/connections")
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_silent_inside_packages_mcp(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path, "server.py", body, subdir="src/a2kit/packages/mcp")
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_cli_builder(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path, "builder.py", body, subdir="src/a2kit/packages/cli")
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_outside_a2kit(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path, "user_app.py", body, subdir="src/myapp")
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


# --------------------------- CLI smoke --------------------------- #


def test_cli_static_command_runs(tmp_path: Path) -> None:
    body = "x = 1\n"
    p = _write(tmp_path, "m.py", body)
    runner = CliRunner()
    # Invoke the lint group's `static` subcommand.
    assert isinstance(cli_main, click.Group)
    result = runner.invoke(cli_main, ["static", str(p)])
    assert result.exit_code == 0, result.output


def test_cli_static_command_reports_findings(tmp_path: Path) -> None:
    body = "import a2kit\n@a2kit.tool()\ndef t() -> str:\n    return 'x'\n"
    p = _write(tmp_path, "m.py", body)
    runner = CliRunner()
    result = runner.invoke(cli_main, ["static", str(p)])
    assert result.exit_code == 1
    assert "A2K002" in result.output


def test_cold_start_no_fastmcp_import() -> None:
    """Importing the lint cli must not pull in fastmcp.

    Runs in a subprocess — clearing fastmcp from sys.modules in-process invalidates
    the FastMCP class identity for sibling tests (isinstance() then fails).
    """
    import subprocess
    import sys

    out = subprocess.check_output(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import a2kit.packages.lint.cli; "
                "print('fastmcp' in sys.modules); "
                "print(any(k.startswith('fastmcp.') for k in sys.modules))"
            ),
        ],
        text=True,
    )
    lines = out.strip().splitlines()
    assert lines[0] == "False"
    assert lines[1] == "False"
