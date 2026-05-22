from __future__ import annotations

import subprocess
import sys
import textwrap


def _run(script: str) -> tuple[float, str]:
    code = textwrap.dedent(script)
    out = subprocess.check_output([sys.executable, "-X", "importtime", "-c", code], stderr=subprocess.STDOUT)
    return 0.0, out.decode()


def _runtime_check(code: str) -> str:
    return subprocess.check_output([sys.executable, "-c", code], text=True)


def test_import_a2kit_under_100ms_and_no_fastmcp() -> None:
    out = _runtime_check(
        "import time, sys;"
        "t0 = time.perf_counter();"
        "import a2kit;"
        "ms = (time.perf_counter() - t0) * 1000;"
        "print(ms);"
        "print('fastmcp' in sys.modules)"
    )
    ms_str, fast_str = out.strip().splitlines()
    assert float(ms_str) < 100, f"import a2kit took {ms_str}ms (>=100ms)"
    assert fast_str == "False", "fastmcp should not load on `import a2kit`"


def test_import_a2kit_does_not_load_typer() -> None:
    """``import a2kit`` must NOT trigger ``import typer``.

    Typer is a runtime dep (powers ``<app> ...`` CLI) but the import must be
    deferred until the user actually constructs the CLI. ``import a2kit`` is
    used by library consumers who never touch the CLI.
    """
    out = _runtime_check("import sys; import a2kit; print('typer' in sys.modules)")
    assert out.strip() == "False", "typer must not load on `import a2kit`"


def test_lint_cli_does_not_load_fastmcp() -> None:
    out = _runtime_check(
        "import sys;"
        "import a2kit.packages.lint.cli;"  # noqa: E501
        "print('fastmcp' in sys.modules)"
    )
    assert out.strip() == "False", "lint CLI must not import fastmcp"


def test_connections_cli_does_not_load_fastmcp() -> None:
    out = _runtime_check(
        "import sys;"
        "import a2kit.packages.connections.cli;"  # noqa: E501
        "print('fastmcp' in sys.modules)"
    )
    assert out.strip() == "False", "connections CLI must not import fastmcp"


def test_otel_package_does_not_eagerly_load_opentelemetry() -> None:
    out = _runtime_check("import sys;import a2kit.packages.otel;print('opentelemetry' in sys.modules)")
    assert out.strip() == "False", "otel package must defer opentelemetry import"


def test_import_a2kit_does_not_load_serve_path() -> None:
    """``import a2kit`` must NOT pull the multiplex-serve path.

    uvicorn (the ASGI server) and ``a2kit.packages.rest`` (the REST
    sub-app) load only on ``serve --transport=http``. A library consumer
    who never serves over HTTP must not pay their import cost.
    """
    out = _runtime_check(
        "import sys; import a2kit;"
        "print('uvicorn' in sys.modules);"
        "print('a2kit.packages.rest' in sys.modules);"
        "print('a2kit.packages.serve' in sys.modules)"
    )
    uvicorn_str, rest_str, serve_str = out.strip().splitlines()
    assert uvicorn_str == "False", "uvicorn must not load on `import a2kit`"
    assert rest_str == "False", "a2kit.packages.rest must not load on `import a2kit`"
    assert serve_str == "False", "a2kit.packages.serve must not load on `import a2kit`"


# --- User-app cold start (with fastmcp loaded) -------------------------- #
#
# Bare ``import a2kit`` must stay <100ms (asserted above). For real user apps
# that build an App, register routers, and run ``--help``, the budget relaxes
# to 200ms — fastmcp is allowed to load (Context type is referenced at app
# build time once we touch tool annotations) but the click CLI tree must
# still come up fast enough that ``my-app --help`` feels instant.

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "examples.streaming_logger.server",
        "examples.elicitation.server",
        "examples.sampling.server",
    ],
)
def test_user_app_help_a2kit_overhead_under_200ms(module: str) -> None:
    """``a2kit``-side cold-start for ``<app> --help`` stays under 200ms.

    This measures the *a2kit + click + user-app* portion only — fastmcp is
    pre-imported before the timer starts. A typical user app needs fastmcp
    loaded (Context type is touched by tool annotations) and that import
    alone is ~1s on most machines, dominated by fastmcp's own dep tree. The
    200ms budget here catches regressions in our own CLI tree construction
    independent of fastmcp's floor — the bare-package <100ms test above
    already guards the cold-start invariant for non-MCP entry points.
    """
    code = (
        "import time, sys;"
        "import fastmcp;"  # pre-warm: fastmcp's own import cost is out of scope
        "t0 = time.perf_counter();"
        f"import {module} as m;"
        "from click.testing import CliRunner;"
        "from a2kit.packages.cli.builder import build_full_cli;"
        "cli = build_full_cli(m.app);"
        "result = CliRunner().invoke(cli, ['--help']);"
        "ms = (time.perf_counter() - t0) * 1000;"
        "print(ms); print(result.exit_code)"
    )
    out = _runtime_check(code)
    ms_str, exit_str = out.strip().splitlines()
    assert exit_str == "0", f"--help exited with {exit_str} for {module}"
    assert float(ms_str) < 200, f"{module} a2kit-overhead --help took {ms_str}ms (>=200ms)"
