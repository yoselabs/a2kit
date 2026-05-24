"""BDD: cold-start invariants for `a2kit.packages.auth`.

Per `auth-spec`:
- `import a2kit` SHALL NOT load `a2kit.packages.auth`.
- `import a2kit.packages.auth` SHALL NOT pull
  `fastmcp.server.auth.providers.*`, `jose` / `python-jose`,
  `cryptography`, `httpx`.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_in_fresh_interpreter(code: str) -> str:
    """Run `code` in a fresh interpreter and return stdout (one snapshot)."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def test_bare_a2kit_import_does_not_load_auth_package() -> None:
    """`import a2kit` MUST NOT touch `a2kit.packages.auth`."""
    out = _run_in_fresh_interpreter("""
        import sys, a2kit
        print('a2kit.packages.auth' in sys.modules)
    """)
    assert out == "False"


def test_auth_package_import_does_not_pull_heavy_provider_deps() -> None:
    """`import a2kit.packages.auth` MUST stay free of `jose`, `httpx`, fastmcp providers."""
    out = _run_in_fresh_interpreter("""
        import sys, a2kit.packages.auth
        forbidden = ['jose', 'python_jose', 'httpx',
                     'fastmcp.server.auth.providers.google']
        print(','.join(m for m in forbidden if m in sys.modules))
    """)
    # An empty string means no forbidden module loaded.
    assert out == "", f"unexpected modules loaded by auth front door: {out}"
