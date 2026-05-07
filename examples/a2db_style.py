"""Example: a2db-style usage — three-part key, no op://, simple DSN.

Run: `uv run python examples/a2db_style.py`
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from a2kit import ConnectionInfo, ConnectionStore, resolve_token


class DbInfo(ConnectionInfo):
    KEY_PARTS = 3
    dsn: str


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        store: ConnectionStore[DbInfo] = ConnectionStore(config_dir, DbInfo)

        os.environ["EXAMPLE_DB_PASSWORD"] = "s3cret"

        store.save(
            DbInfo(
                key=("acme", "prod", "main"),
                dsn="postgresql://user:${EXAMPLE_DB_PASSWORD}@db.acme.io/main",
            )
        )

        loaded = store.load(("acme", "prod", "main"))
        print(f"key: {loaded.key}")
        print(f"raw dsn: {loaded.dsn}")
        print(f"resolved dsn: {resolve_token(loaded.dsn)}")
        print(f"all connections: {[info.key for info in store.list_connections()]}")


if __name__ == "__main__":
    main()
