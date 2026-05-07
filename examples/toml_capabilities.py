"""Example: TOML-based capability declarations (v0.4).

`MCPRunner.__init__` reads `[tool.a2kit.capabilities]` at startup and registers
each entry. Authors who prefer code-side `a2kit.capabilities.register(...)` are
unaffected — both work, both validate against the same Pydantic model.

Run: `uv run python examples/toml_capabilities.py`
"""

from __future__ import annotations

import os
from pathlib import Path

import a2kit


class _FakeServer:
    settings = type("S", (), {"host": "h", "port": 1})()

    def run(self, transport: str = "stdio") -> None:
        pass


def main() -> None:
    # Build a temporary pyproject.toml to demonstrate.
    import tempfile

    workdir = Path(tempfile.mkdtemp())
    (workdir / "pyproject.toml").write_text(
        "[tool.a2kit.runner]\n"
        'default_select = "default and not write"\n'
        "\n"
        "[tool.a2kit.capabilities]\n"
        '"tickets-management" = { description = "Issue/sprint/comment management" }\n'
        '"reports" = { description = "Read-only analytics" }\n'
    )
    cwd = Path.cwd()
    try:
        os.chdir(workdir)
        # MCPRunner picks up pyproject on init.
        a2kit.MCPRunner(_FakeServer())
        for name in ("tickets-management", "reports"):
            rec = a2kit.capabilities.get(name)
            print(f"registered: {name} = {rec.description if rec else '<missing>'}")
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    main()
