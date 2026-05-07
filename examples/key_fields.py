"""Example: KEY_FIELDS = ("project", "env", "db") with all four call shapes.

Run: `uv run python examples/key_fields.py`
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import a2kit


class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")
    base_url: str
    api_key: str


def main() -> None:
    store: a2kit.ConnectionStore[WidgetConn] = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    store.save(WidgetConn(key=("acme", "prod", "main"), base_url="https://api", api_key="x"))

    # 1. kwargs (preferred):
    print("kwargs:    ", store.load(project="acme", env="prod", db="main").base_url)
    # 2. tuple (migration path):
    print("tuple:     ", store.load(("acme", "prod", "main")).base_url)
    # 3. list:
    print("list:      ", store.load(["acme", "prod", "main"]).base_url)
    # 4. positional:
    print("positional:", store.load("acme", "prod", "main").base_url)

    # Errors are typed:
    try:
        store.load(project="acme", env="prod")  # missing 'db'
    except a2kit.KeyFieldMissing as exc:
        print("missing kwarg ->", exc)

    try:
        store.load(("acme", "prod"))  # wrong arity
    except a2kit.KeyArityMismatch as exc:
        print("arity mismatch ->", exc)


if __name__ == "__main__":
    main()
