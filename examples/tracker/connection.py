from __future__ import annotations

from a2kit.packages.connections import ConnectionConfig


class TrackerConn(ConnectionConfig):
    db_path: str
    token: str = ""
    read_only: bool = False
