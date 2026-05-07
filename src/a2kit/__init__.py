"""a2kit — thin library for FastMCP-based MCPs (v0.8.0).

Composes with FastMCP. Does NOT replace it. Every primitive is opt-in; drop down
to FastMCP at any boundary stays clean. See README for the full rundown.

v0.7 highlights (idiomatic Python pass):

- **`Cap` is now `StrEnum`**. `Cap.WRITE == "write"` is True; `list(Cap)` works;
  `Cap("write")` parses raw strings.
- **`*, info: ConnT | None = None` kwarg pattern is removed.** Use
  `MyRouter.context.info()` (the only API now).
- **Auto-injected param docs.** A function with `connection_param="conn"` no
  longer needs `f"... {connection_param_doc()}"` in its docstring; the decorator
  prepends it at decoration time. New `A2K013` lint rule flags leftover f-string
  helpers as advisory.
- **`ToolKwargs` is public.** Use `Unpack[ToolKwargs]` for higher-order Router
  classmethod factories.
- **FQN-based `_RouterContext` naming.** Two same-named Router classes in
  different modules no longer share state.
- **`A2K012` re-export resolution.** A `Final[str]` constant re-exported via
  `pkg/__init__.py` is now recognised (cap depth 3).
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
from a2kit._tool_kwargs import ToolKwargs
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
    ToolCallContamination,
    WriteNotAllowed,
)
from a2kit.formatter import Response, format_response
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

__version__ = "0.8.0"

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
    "Response",
    "Router",
    "RouterRegistry",
    "RunnerConfig",
    "SchemaSnapshotMismatch",
    "SelectAtom",
    "SelectExpr",
    "TokenResolutionError",
    "ToolCallContamination",
    "ToolConfig",
    "ToolKwargs",
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
