"""a2kit — thin library for FastMCP-based MCPs (v0.10.0).

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

from a2kit import docs, enrichers, formatter, lint, projection, scaffold, testing, tools
from a2kit._capabilities import (
    Cap,
    Capability,
    CapabilityRecord,
    UnknownCapability,
    capabilities,
)
from a2kit._configs import BudgetConfig, RunnerConfig
from a2kit._otel import get_tracer, plugin_span
from a2kit._select import SelectAtom, SelectExpr, parse_select, sel
from a2kit._tool_kwargs import ToolKwargs
from a2kit.app import App
from a2kit.connections import (
    ENV_CONFIG_HOME,
    ConnectionConfig,
    ConnectionInfoLike,
    ConnectionStore,
    ConnectionStoreLike,
    default_config_dir,
)
from a2kit.di import (
    Depends,
    DependsCycleError,
)
from a2kit.enrichers import (
    EnricherFn,
    chain,
    connection_enricher,
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
from a2kit.formatter import (
    ListViewMode,
    Local,
    Page,
    Passthrough,
    Response,
    format_response,
)
from a2kit.scaffold import (
    FastMCPLike,
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
from a2kit.tools import ToolMetadata, tool, tool_metadata
from a2kit.tools._verbs import list as list_tool
from a2kit.tools._verbs import read as read_tool
from a2kit.tools._verbs import write as write_tool

# v0.12: surface verbs as `a2kit.list / a2kit.read / a2kit.write`. We bind the
# module attributes directly (rather than `from ... import list`) so the
# imported `list` doesn't shadow the builtin within this module.
list = list_tool  # noqa: A001 — intentional: external callers use `a2kit.list`
read = read_tool
write = write_tool

__version__ = "0.16.0.dev0"

__all__ = [
    "ENV_CONFIG_HOME",
    "A2KitError",
    "App",
    "BudgetConfig",
    "Cap",
    "Capability",
    "CapabilityRecord",
    "ConnectionConfig",
    "ConnectionInfoLike",
    "ConnectionNotFound",
    "ConnectionStore",
    "ConnectionStoreLike",
    "Depends",
    "DependsCycleError",
    "EnricherFn",
    "EnvVarNotFound",
    "FastMCPLike",
    "InvalidConnectionKey",
    "InvalidFilterExpression",
    "InvalidToolReturnTypeError",
    "KeyArityMismatch",
    "KeyFieldMissing",
    "ListViewMode",
    "Local",
    "MCPRunner",
    "MigrationRequired",
    "OpResolutionError",
    "Page",
    "Passthrough",
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
    "ToolKwargs",
    "ToolMetadata",
    "UnknownCapability",
    "WriteNotAllowed",
    "__version__",
    "build_cli",
    "capabilities",
    "chain",
    "connection_enricher",
    "default_config_dir",
    "default_registry",
    "docs",
    "enrichers",
    "format_response",
    "formatter",
    "get_tracer",
    "lint",
    "list",
    "parse_select",
    "plugin_span",
    "projection",
    "read",
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
    "tool_metadata",
    "tools",
    "write",
]


def __getattr__(name: str) -> object:
    """Removed-API guards: emit a helpful migration hint instead of `AttributeError`."""
    if name == "Feature":
        msg = "`a2kit.Feature` was removed in v0.4. Use `a2kit.Router` instead (kwarg-init: `Router(name='issues', ...)`)."
        raise ImportError(msg)
    if name == "FeatureRegistry":
        msg = "`a2kit.FeatureRegistry` was removed in v0.4. Use `a2kit.RouterRegistry`."
        raise ImportError(msg)
    if name == "A2KIT_CONFIG_HOME":
        msg = "`a2kit.A2KIT_CONFIG_HOME` was removed in v0.11 (it was a self-alias). Use `a2kit.ENV_CONFIG_HOME` instead."
        raise ImportError(msg)
    msg = f"module 'a2kit' has no attribute {name!r}"
    raise AttributeError(msg)
