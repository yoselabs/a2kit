"""a2kit — thin library for FastMCP-based MCPs (v0.3.1).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

v0.3.1 highlights:

- `Router` (was `Feature`) is a Pydantic BaseModel with auto-tagging.
- `Cap` constants + `capabilities` registry namespace + `UnknownCapability`.
- `--select` boolean expression replaces `--enable`/`--no-enable`/`--writes`.
- Typed builder `a2kit.sel(...)` mirrors the CLI grammar.
- Pydantic configs (`ToolConfig`, `RunnerConfig`, `BudgetConfig`).
- KEY_FIELDS validated via `@model_validator` on `ConnectionInfo`.
"""

from __future__ import annotations

from a2kit import docs, errors, formatter, lint, scaffold, testing, tools
from a2kit._capabilities import (
    Cap,
    Capability,
    CapabilityRecord,
    UnknownCapability,
    capabilities,
)
from a2kit._configs import BudgetConfig, RunnerConfig, ToolConfig
from a2kit._select import SelectAtom, SelectExpr, parse_select, sel
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
from a2kit.scaffold import (
    Feature,
    FeatureRegistry,
    MCPRunner,
    Router,
    RouterRegistry,
    build_cli,
    register_ephemeral_connections,
    scope_filter,
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

# A2KIT_CONFIG_HOME — re-export with the canonical name expected in the v0.3.1
# spec (matches the env var documented in `a2kit.connections`).
A2KIT_CONFIG_HOME = ENV_CONFIG_HOME

__version__ = "0.3.1"

__all__ = [
    "A2KIT_CONFIG_HOME",
    "ENV_CONFIG_HOME",
    "A2KitError",
    "BudgetConfig",
    "Cap",
    "Capability",
    "CapabilityRecord",
    "ConnectionInfo",
    "ConnectionNotFound",
    "ConnectionNotFoundEnricher",
    "ConnectionStore",
    "EnricherRegistry",
    "EnvVarNotFound",
    "ErrorEnricher",
    "Feature",
    "FeatureRegistry",
    "InvalidConnectionKey",
    "InvalidToolReturnTypeError",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "MCPRunner",
    "OpResolutionError",
    "ResolverRegistry",
    "Router",
    "RouterRegistry",
    "RunnerConfig",
    "SchemaSnapshotMismatch",
    "SelectAtom",
    "SelectExpr",
    "TokenResolutionError",
    "ToolConfig",
    "ToolXMLContamination",
    "UnknownCapability",
    "WriteNotAllowed",
    "__version__",
    "build_cli",
    "capabilities",
    "default_config_dir",
    "default_registry",
    "docs",
    "errors",
    "formatter",
    "lint",
    "parse_select",
    "register_ephemeral_connections",
    "resolve_env",
    "resolve_literal",
    "resolve_op",
    "resolve_token",
    "scaffold",
    "scope_filter",
    "sel",
    "testing",
    "tool",
    "tools",
]
