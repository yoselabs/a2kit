"""a2kit.packages.connections — pydantic-settings-backed Connection store + CLI + plugin."""

from a2kit.exceptions import WriteNotAllowed
from a2kit.packages.connections.config import ConnectionConfig, default_config_dir
from a2kit.packages.connections.exceptions import (
    ConnectionKwargMissing,
    ConnectionNotFound,
    ConnectionNotRegistered,
    EnvVarNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
    OpResolutionError,
    StoreConnectionTypeUnknown,
    TokenResolutionError,
)
from a2kit.packages.connections.factory import get_conn_factory
from a2kit.packages.connections.filters import EphemeralAwareStore, FilteredStore, scope_filter
from a2kit.packages.connections.plugin import Connections
from a2kit.packages.connections.store import ConnectionStore
from a2kit.packages.connections.store_marker import Store

__all__ = [
    "ConnectionConfig",
    "ConnectionKwargMissing",
    "ConnectionNotFound",
    "ConnectionNotRegistered",
    "ConnectionStore",
    "Connections",
    "EnvVarNotFound",
    "EphemeralAwareStore",
    "FilteredStore",
    "InvalidConnectionKey",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "OpResolutionError",
    "Store",
    "StoreConnectionTypeUnknown",
    "TokenResolutionError",
    "WriteNotAllowed",
    "default_config_dir",
    "get_conn_factory",
    "scope_filter",
]
