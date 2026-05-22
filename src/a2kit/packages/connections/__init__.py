"""a2kit.packages.connections — pydantic-settings-backed Connection store + CLI.

The single-call installer lives in :mod:`a2kit.packages.connections.install`;
the store, config, filters, dispatch hook, and CLI live in their own
submodules.
"""

from __future__ import annotations

from a2kit.packages.connections.config import ConnectionConfig, default_config_dir
from a2kit.packages.connections.exceptions import (
    ConnectionNotFound,
    EnvVarNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
    OpResolutionError,
    TokenResolutionError,
    WriteNotAllowed,
)
from a2kit.packages.connections.filters import EphemeralAwareStore, FilteredStore, scope_filter
from a2kit.packages.connections.install import install_connections
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
    "install_connections",
    "scope_filter",
]
