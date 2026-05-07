"""a2kit — thin library for FastMCP-based MCPs (v0.4.0).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

v0.4 highlights:

- All v0.3 deprecation aliases removed (clean cut, pre-1.0).
- CEL projection / filter primitive (`a2kit.projection`, `[projection]` extra).
- `a2kit.format_response(data, *, filter=, fields=, ...)` composes filter +
  projection + truncation.
- Auto-load `[tool.a2kit.runner] default_select` and `[tool.a2kit.capabilities]`
  from `pyproject.toml`.
- A2K010 lint activated (validates `--select` atoms against the registry).
- A2K011 advisory (prefer Pydantic return types over raw `dict`).
- A2K005 completed (cross-checks tool param types against `KEY_FIELDS` arity).
- `_select.py` split into `_select_parse.py` + `_select_eval.py`.
"""

from __future__ import annotations

from a2kit import docs, errors, formatter, lint, projection, scaffold, testing, tools
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
    InvalidFilterExpression,
    InvalidToolReturnTypeError,
    KeyArityMismatch,
    KeyFieldMissing,
    OpResolutionError,
    ProjectionUnavailable,
    SchemaSnapshotMismatch,
    TokenResolutionError,
    ToolXMLContamination,
    WriteNotAllowed,
)
from a2kit.formatter import format_response
from a2kit.scaffold import (
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

A2KIT_CONFIG_HOME = ENV_CONFIG_HOME

__version__ = "0.4.0"

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
    "InvalidConnectionKey",
    "InvalidFilterExpression",
    "InvalidToolReturnTypeError",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "MCPRunner",
    "OpResolutionError",
    "ProjectionUnavailable",
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
    "format_response",
    "formatter",
    "lint",
    "parse_select",
    "projection",
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


def __getattr__(name: str) -> object:
    """Removed-API guards: emit a helpful migration hint instead of `AttributeError`."""
    if name == "Feature":
        msg = "`a2kit.Feature` was removed in v0.4. Use `a2kit.Router` instead (kwarg-init: `Router(name='issues', ...)`)."
        raise ImportError(msg)
    if name == "FeatureRegistry":
        msg = "`a2kit.FeatureRegistry` was removed in v0.4. Use `a2kit.RouterRegistry`."
        raise ImportError(msg)
    msg = f"module 'a2kit' has no attribute {name!r}"
    raise AttributeError(msg)
