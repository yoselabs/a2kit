"""a2kit.packages.connections — pydantic-settings-backed Connection store + CLI."""

from a2kit.exceptions import WriteNotAllowed
from a2kit.packages.connections.config import ConnectionConfig, default_config_dir
from a2kit.packages.connections.exceptions import (
    ConnectionNotFound,
    EnvVarNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
    OpResolutionError,
    TokenResolutionError,
)
from a2kit.packages.connections.factory import get_conn_factory
from a2kit.packages.connections.filters import EphemeralAwareStore, FilteredStore, scope_filter
from a2kit.packages.connections.store import ConnectionStore

__all__ = [
    "ConnectionConfig",
    "ConnectionNotFound",
    "ConnectionStore",
    "EnvVarNotFound",
    "EphemeralAwareStore",
    "FilteredStore",
    "InvalidConnectionKey",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "OpResolutionError",
    "TokenResolutionError",
    "WriteNotAllowed",
    "default_config_dir",
    "get_conn_factory",
    "scope_filter",
]
