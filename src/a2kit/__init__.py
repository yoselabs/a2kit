"""a2kit — thin library for FastMCP-based MCPs (v0.2).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

Public API (v0.2):

- `a2kit.connections` — `ConnectionInfo`, `ConnectionStore`, `default_config_dir`.
- `a2kit.tokens` — `resolve_token`, `ResolverRegistry`, individual resolvers.
- `a2kit.tools` — fat `tool` decorator (re-exported as `a2kit.tool`),
  `preserve_return_annotation`, `assert_clean_string`.
- `a2kit.errors` — `ErrorEnricher` protocol, `EnricherRegistry`,
  `ConnectionNotFoundEnricher`.
- `a2kit.scaffold` — `build_cli`, `register_ephemeral_connections`,
  `scope_filter`, `MCPRunner`, `FeatureRegistry`.
- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`.
- `a2kit.docs` — `connection_param_doc`.
- `a2kit.testing` — `snapshot_schemas`, `assert_schemas_match`, `cassette`.
- `a2kit.pytest_plugin` — opt-in pytest plugin; provides `schema_snapshot`,
  `update_cassettes` fixtures and `--update-schema-snapshots`,
  `--update-cassettes` flags.
- exceptions — `A2KitError` (root) plus typed subclasses.
"""

from __future__ import annotations

from a2kit import docs, errors, formatter, scaffold, testing, tools
from a2kit.connections import (
    ENV_CONFIG_HOME,
    ConnectionInfo,
    ConnectionStore,
    default_config_dir,
)
from a2kit.errors import (
    ConnectionNotFoundEnricher,
    EnricherRegistry,
    ErrorEnricher,
)
from a2kit.exceptions import (
    A2KitError,
    ConnectionNotFound,
    EnvVarNotFound,
    InvalidConnectionKey,
    InvalidToolReturnTypeError,
    OpResolutionError,
    SchemaSnapshotMismatch,
    TokenResolutionError,
    ToolXMLContamination,
    WriteNotAllowed,
)
from a2kit.tokens import (
    ResolverRegistry,
    default_registry,
    resolve_env,
    resolve_literal,
    resolve_op,
    resolve_token,
)
from a2kit.tools import tool

__version__ = "0.2.0"

__all__ = [
    "ENV_CONFIG_HOME",
    "A2KitError",
    "ConnectionInfo",
    "ConnectionNotFound",
    "ConnectionNotFoundEnricher",
    "ConnectionStore",
    "EnricherRegistry",
    "EnvVarNotFound",
    "ErrorEnricher",
    "InvalidConnectionKey",
    "InvalidToolReturnTypeError",
    "OpResolutionError",
    "ResolverRegistry",
    "SchemaSnapshotMismatch",
    "TokenResolutionError",
    "ToolXMLContamination",
    "WriteNotAllowed",
    "__version__",
    "default_config_dir",
    "default_registry",
    "docs",
    "errors",
    "formatter",
    "resolve_env",
    "resolve_literal",
    "resolve_op",
    "resolve_token",
    "scaffold",
    "testing",
    "tool",
    "tools",
]
