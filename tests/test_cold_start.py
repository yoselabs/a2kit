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
