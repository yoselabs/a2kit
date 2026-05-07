"""a2kit — thin library for FastMCP-based MCPs (v0.5.0).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

v0.5 highlights:

- **Breaking:** `KEY_FIELDS: ClassVar[tuple[str, ...]]` is gone. Connection keys
  are now NamedTuple-based: `class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey)`.
  Subclasses still using `KEY_FIELDS` raise `MigrationRequired` at class creation.
- `cls.Key` is the canonical NamedTuple per subclass; default is `_DefaultKey(name: str)`.
- `Literal[...]` per-field typing now possible (e.g. `env: Literal["dev","staging","prod"]`).
- `store.load(WidgetKey(...))` joins the existing tuple/positional/kwargs/bare-string shapes.
- A2K005 simplified: detects leftover `KEY_FIELDS` (lint-time migration aid) and
  cross-checks tool `connection_param` arity against `cls.Key._fields`.
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
    MigrationRequired,
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

__version__ = "0.5.0"

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
    "MigrationRequired",
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
