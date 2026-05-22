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
    """App-scope resource owning the (fake) sqlite open/close pair.

    v0.36 lazy first-use: ``__aenter__`` runs on first ``Container.get``,
    not eagerly at ``async with app:``. The ``_sqlite_open`` health check
    below declares the resource as a parameter, which forces resolution
    (and entry) when the health tool runs.
    """

    async def __aenter__(self) -> _SqliteResource:
        _state.sqlite_open = True
        return self

    async def __aexit__(self, *_exc: object) -> None:
        _state.sqlite_open = False


builder = a2kit.AppBuilder("health-demo")
builder.provide(_SqliteResource)


@builder.health_check
async def _ping() -> a2kit.HealthResult:
    """Trivial liveness check — always ok."""
    return a2kit.HealthResult.ok()


@builder.health_check
async def _sqlite_open(sqlite: _SqliteResource) -> a2kit.HealthResult:
    """Readiness gate — declares the resource so resolution enters it."""
    if not _state.sqlite_open:
        return a2kit.HealthResult.fail("sqlite not opened yet")
    return a2kit.HealthResult.ok()


app = builder.build()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
