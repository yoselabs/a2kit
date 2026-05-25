"""a2effect isolation gates (Group 17).

a2effect is a standalone foundation: no a2kit imports, and importing
a2kit does not eagerly pull any of the third-party libraries that
raises_registry stubs cover (httpx / asyncpg / redis / sqlalchemy).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _runtime_check(code: str) -> str:
    return subprocess.check_output([sys.executable, "-c", code], text=True)


def test_a2effect_source_has_no_a2kit_imports() -> None:
    """a2effect SHALL NOT import a2kit (one-way dependency)."""
    root = Path(__file__).parent.parent / "packages" / "a2effect" / "src"
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import a2kit", "from a2kit")):
                offenders.append(f"{py}: {stripped}")
    assert not offenders, "a2effect leaked a2kit imports:\n" + "\n".join(offenders)


def test_import_a2kit_does_not_load_raises_registry_targets() -> None:
    """`import a2kit` SHALL NOT eagerly load httpx/asyncpg/redis/sqlalchemy.

    raises_registry ships JSON-based stubs for these libraries; the real
    libs must remain optional, loaded only by consumers that use them.
    """
    out = _runtime_check(
        "import sys; import a2kit;"
        "print('httpx' in sys.modules);"
        "print('asyncpg' in sys.modules);"
        "print('redis' in sys.modules);"
        "print('sqlalchemy' in sys.modules)"
    )
    httpx_, asyncpg_, redis_, sqla_ = out.strip().splitlines()
    assert httpx_ == "False", "httpx must not load on `import a2kit`"
    assert asyncpg_ == "False", "asyncpg must not load on `import a2kit`"
    assert redis_ == "False", "redis must not load on `import a2kit`"
    assert sqla_ == "False", "sqlalchemy must not load on `import a2kit`"


def test_import_a2effect_does_not_load_raises_registry_targets() -> None:
    """`import a2effect` SHALL NOT eagerly load the third-party stub libs."""
    out = _runtime_check(
        "import sys; import a2effect;"
        "print('httpx' in sys.modules);"
        "print('asyncpg' in sys.modules);"
        "print('redis' in sys.modules);"
        "print('sqlalchemy' in sys.modules)"
    )
    httpx_, asyncpg_, redis_, sqla_ = out.strip().splitlines()
    assert httpx_ == "False"
    assert asyncpg_ == "False"
    assert redis_ == "False"
    assert sqla_ == "False"
