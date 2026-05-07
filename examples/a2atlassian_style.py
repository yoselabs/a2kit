"""Example: a2atlassian-style usage — flat key, ${ENV_VAR} token, read_only field.

Note: `op://` resolution requires the 1Password CLI; this example uses ${ENV_VAR}
to keep the script self-contained. Replace with `op://vault/item/field` in real use.

Run: `uv run python examples/a2atlassian_style.py`
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from a2kit import ConnectionInfo, ConnectionStore, resolve_token


class AtlassianInfo(ConnectionInfo):
    KEY_FIELDS = ("name",)
    url: str
    email: str
    token: str
    read_only: bool = True


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config_dir = Path(tmp)
        store: ConnectionStore[AtlassianInfo] = ConnectionStore(config_dir, AtlassianInfo)

        os.environ["EXAMPLE_ATLASSIAN_TOKEN"] = "atl-token-xyz"

        store.save(
            AtlassianInfo(
                key=("prod",),
                url="https://prod.atlassian.net",
                email="dt@example.com",
                token="${EXAMPLE_ATLASSIAN_TOKEN}",
                read_only=False,
            )
        )

        loaded = store.load(("prod",))
        print(f"connection: {loaded.key[0]}")
        print(f"url: {loaded.url}")
        print(f"read_only: {loaded.read_only}")
        print(f"raw token: {loaded.token}")
        print(f"resolved token: {resolve_token(loaded.token)}")


if __name__ == "__main__":
    main()
