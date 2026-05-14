"""Built-in `_meta.health` tool + `@app.health_check` demo.

Two readiness probes — one always passes, one flips based on a fake state
flag — show how aggregated status flips between ``ok`` and ``degraded``.

Run::

    python -m examples.health_demo.server health         # CLI shorthand
    python -m examples.health_demo.server _meta health   # via the meta router
    python -m examples.health_demo.server serve          # MCP server (health hidden from list_tools)
"""

from __future__ import annotations

from dataclasses import dataclass

import a2kit


@dataclass
class _State:
    sqlite_open: bool = False


_state = _State()


class _SqliteResource:
    """Singleton owning the (fake) sqlite open/close pair.

    v0.35: the framework auto-detects ``__aenter__``/``__aexit__`` on
    resolved singletons and wires them into the App's lifecycle.
    """

    async def __aenter__(self) -> _SqliteResource:
        _state.sqlite_open = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        _state.sqlite_open = False


app = a2kit.App("health-demo")
app.singleton(_SqliteResource)


@app.health_check
async def _ping() -> a2kit.HealthResult:
    """Trivial liveness check — always ok."""
    return a2kit.HealthResult.ok()


@app.health_check
async def _sqlite_open() -> a2kit.HealthResult:
    """Readiness gate — passes only after lifecycle opened sqlite."""
    if not _state.sqlite_open:
        return a2kit.HealthResult.fail("sqlite not opened yet (lifecycle hasn't run)")
    return a2kit.HealthResult.ok()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
