"""CLI/MCP entrypoint scaffolding helpers.

Provides building blocks — NOT a `main()`. The MCP author owns the FastMCP
server instance and the program entry; a2kit only ships the recurring chunks.

v0.11: split from a single `scaffold.py` into a package. Public surface is
unchanged — `from a2kit.scaffold import MCPRunner, Router, ...` still works.
The internal modules are:

- `_cli.py`     — `build_cli`, `register_ephemeral_connections`, argv parsers
- `_stores.py`  — `_EphemeralAwareStore`, `_FilteredStore`, `scope_filter`
- `_routers.py` — `Router`, `RouterRegistry`, slug helpers
- `_runner.py`  — `MCPRunner`, `FastMCPLike`, pyproject loader, expr helpers
"""

from a2kit.scaffold._cli import (
    RegisterBlock,
    _parse_key_arg,
    _parse_kv_pair,
    _parse_multistore_register,
    build_cli,
    register_ephemeral_connections,
)
from a2kit.scaffold._routers import (
    Router,
    RouterRegistry,
    _RegisterableRouter,
    _RouterEntry,
    _slugify,
)
from a2kit.scaffold._runner import (
    FastMCPLike,
    MCPRunner,
    RunnerOptions,
    _atom_polarity,
    _expr_mentions,
    _find_pyproject,
    _load_pyproject_a2kit,
    _register_pyproject_capabilities,
)
from a2kit.scaffold._stores import (
    _EphemeralAwareStore,
    _FilteredStore,
    scope_filter,
)

__all__ = [
    "FastMCPLike",
    "MCPRunner",
    "RegisterBlock",
    "Router",
    "RouterRegistry",
    "RunnerOptions",
    "_EphemeralAwareStore",
    "_FilteredStore",
    "_RegisterableRouter",
    "_RouterEntry",
    "_atom_polarity",
    "_expr_mentions",
    "_find_pyproject",
    "_load_pyproject_a2kit",
    "_parse_key_arg",
    "_parse_kv_pair",
    "_parse_multistore_register",
    "_register_pyproject_capabilities",
    "_slugify",
    "build_cli",
    "register_ephemeral_connections",
    "scope_filter",
]
