"""a2kit — thin library for FastMCP-based MCPs (v0.3).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

Public API (v0.3):

- `a2kit.connections` — `ConnectionInfo` (now with `KEY_FIELDS`),
  `ConnectionStore` (now exposes `connection_class`), `default_config_dir`.
- `a2kit.tokens` — `resolve_token`, `ResolverRegistry`, individual resolvers.
- `a2kit.tools` — fat `tool` decorator (re-exported as `a2kit.tool`); v0.3
  adds `server=` for auto-registration.
- `a2kit.errors` — `ErrorEnricher` protocol, `EnricherRegistry`,
  `ConnectionNotFoundEnricher`.
- `a2kit.scaffold` — `build_cli`, `register_ephemeral_connections`,
  `scope_filter`, `MCPRunner`, `FeatureRegistry`, `Feature` (v0.3).
- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`.
- `a2kit.docs` — `connection_param_doc`, `register_param_doc`, `param_doc` (v0.3).
- `a2kit.testing` — `snapshot_schemas`, `assert_schemas_match`, `cassette`.
- `a2kit.lint` — `run_static_rules`, `run_runtime_checks`, CLI `main` (v0.3).
- `a2kit.pytest_plugin` — opt-in pytest plugin.
- exceptions — `A2KitError` plus typed subclasses (incl. v0.3
  `KeyFieldMissing`, `KeyArityMismatch`).
"""

from __future__ import annotations

from a2kit import docs, errors, formatter, lint, scaffold, testing, tools
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
    KeyArityMismatch,
    KeyFieldMissing,
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

__version__ = "0.3.0"

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
    "KeyArityMismatch",
    "KeyFieldMissing",
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
    "lint",
    "resolve_env",
    "resolve_literal",
    "resolve_op",
    "resolve_token",
    "scaffold",
    "testing",
    "tool",
    "tools",
]
