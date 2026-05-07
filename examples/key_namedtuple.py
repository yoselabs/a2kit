"""Example: NamedTuple `key=` migration — five `load()` call shapes.

Run: `uv run python examples/key_namedtuple.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import NamedTuple

import a2kit


class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str


class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    base_url: str
    api_key: str


def main() -> None:
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(
        WidgetConn(
            key=WidgetKey(project="acme", env="prod", db="main"),
            base_url="https://api",
            api_key="x",
        )
    )

    # 1. Typed NamedTuple instance — most explicit, fully type-checked.
    print("namedtuple:", store.load(WidgetKey(project="acme", env="prod", db="main")).base_url)
    # 2. kwargs (preferred for ad-hoc).
    print("kwargs:    ", store.load(project="acme", env="prod", db="main").base_url)
    # 3. tuple (migration path from v0.4).
    print("tuple:     ", store.load(("acme", "prod", "main")).base_url)
    # 4. list.
    print("list:      ", store.load(["acme", "prod", "main"]).base_url)
    # 5. positional.
    print("positional:", store.load("acme", "prod", "main").base_url)

    # Errors are typed and reference the NamedTuple class name:
    try:
        store.load(project="acme", env="prod")  # missing 'db'
    except a2kit.KeyFieldMissing as exc:
        print("missing kwarg ->", exc)

    try:
        store.load(("acme", "prod"))  # wrong arity
    except a2kit.KeyArityMismatch as exc:
        print("arity mismatch ->", exc)

    # store.list_keys() returns NamedTuple instances — not raw tuples:
    keys = store.list_keys()
    print("list_keys:", keys)
    print("first .project:", keys[0].project)


if __name__ == "__main__":
    main()
