"""Example: per-field `Literal` typing on a NamedTuple key — type-system enforcement.

This demonstrates the v0.5 win that v0.4's `KEY_FIELDS: tuple[str, ...]` could not give:
field-level types. Pass `env="production"` and ty / pyright reject it at type-check
time, before the call ever runs.

Run: `uv run python examples/typed_key_literal.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal, NamedTuple

import a2kit


class WidgetKey(NamedTuple):
    project: str
    env: Literal["dev", "staging", "prod"]  # ty rejects env="production"
    db: str


class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    base_url: str


def main() -> None:
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(WidgetConn(key=WidgetKey(project="acme", env="prod", db="main"), base_url="https://api"))

    info = store.load(WidgetKey(project="acme", env="prod", db="main"))
    print("loaded:", info.base_url)

    # The next call would fail ty/pyright at type-check time:
    #     store.load(WidgetKey(project="acme", env="production", db="main"))
    # ty: error: Argument of type 'Literal["production"]' cannot be assigned to
    #            parameter 'env' of type 'Literal["dev", "staging", "prod"]'
    #
    # At runtime the construction itself succeeds (NamedTuple does not enforce
    # Literal narrowing — that's the type-checker's job). Pydantic still validates
    # the resulting tuple via `_validate_key`.


if __name__ == "__main__":
    main()
