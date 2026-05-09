## Why

a2kit markets itself as "thin lib on top of FastMCP," but the source contradicts the claim: 94 Python files, 43 underscore-prefixed modules in `src/`, and seven sub-systems packaged as one library. Worse: a2kit doesn't actually depend on FastMCP today — it uses a `FastMCPLike` Protocol and reinvents DI, middleware chaining, OTel wrapping, structlog wrapping, a CEL-style select grammar, and more.

Verified findings (2026-05-09):

- **FastMCP 3.2.4 ships its own DI** via `uncalled_for==0.3.2` (`Dependency`, `Depends`, `Shared` for singletons, `SharedContext` for test isolation). Same `Annotated[T, Depends(factory)]` idiom a2kit reimplements.
- **FastMCP ships full middleware** with hook set `on_call_tool`/`on_list_tools`/`on_initialize`/`on_request`/etc., plus 10 built-in middlewares: `authorization`, `caching`, `error_handling`, `logging`, `ping`, `rate_limiting`, `response_limiting`, `timing`, `tool_injection`.
- **The MCP standard defines `ToolAnnotations`** (`readOnlyHint`, `destructiveHint`) and FastMCP's `tool()` accepts both `annotations=` and `tags=`. a2kit's `@read`/`@write`/`@list` verbs are sugar over those; a2kit's capability tags map to FastMCP `tags`.
- **FastMCP exposes context primitives** (`CurrentContext`, `CurrentFastMCP`, `CurrentRequest`, `CurrentHeaders`, `Progress`).

The skeptical reader closes the tab on "AI slop" before evaluation. External adoption is zero. This is the only window where breakage is free.

## What Changes

**Architecture: protocol-agnostic core + per-protocol adapters.** The `@tool` decorator stamps protocol-neutral metadata onto functions; FastMCP knowledge lives only in `packages/mcp/`; CLI knowledge lives only in `packages/cli/`. CLI tool invocations never load fastmcp (~318ms cold-start vs ~3.6s with fastmcp). MCP server startup (`fastmcp run`) loads fastmcp once.

DI uses **`uncalled_for` directly** with parameter-default form: `*, conn: Conn = Depends(get_conn)`. a2kit's bespoke `Annotated[T, Depends(fn)]` resolver is deleted.

### Core (top-level files in `src/a2kit/`) — protocol-agnostic, fastmcp-free

`app.py`, `tool.py`, `signature.py`, `routers.py`, `capabilities.py`, `exceptions.py`. Estimated ~9 files, ~1.0K LOC.

(`signature.py` parses `T = Depends(fn)` parameter-default form using `uncalled_for` directly. No `metadata.py` — tool metadata is stamped onto the function as `fn._a2kit = {...}` and copied to FastMCP `Tool.meta["a2kit"]` at adapter time. No `runner.py` or `cli.py` at core level — those are adapter concerns.)

### Plugin packages (under `src/a2kit/packages/`)

a2kit core works without any of these. Each is opt-in. Adapters depend on their protocol library; non-adapter packages depend only on what they need.

- `mcp/` — **the FastMCP adapter.** `build_mcp_server(app)` returns a FastMCP instance with all tools registered via `FunctionTool.from_function(fn, name=..., tags=..., annotations=..., meta={"a2kit": {...}}) + server.add_tool(tool)`. Includes a2kit-unique middlewares (`listview`, `guards`, `enricher`) as `fastmcp.server.middleware.Middleware` subclasses. **Only place fastmcp is imported.** ~250 LOC.
- `cli/` — **the Click adapter.** `build_cli(app)` returns a Click group with **progressive disclosure**: top level shows Routers as subgroups + `connections` as a built-in subgroup; each Router subgroup shows its tools. Tools invoke in-process via `uncalled_for.without_dependencies(fn)` + Click-parsed kwargs. **Only place click + uncalled_for runtime resolution is wired.** ~200 LOC.
- `connections/` — ConnectionStore + ConnectionConfig under **Contract B**: pydantic-settings native; eager `${VAR}` / `op://` resolution at config load time; cloud secret backends (AWS/Azure/GCP Secrets Manager) free via pydantic-settings sources. `get_conn_factory`, `scope_filter`. ~400 LOC.
- `enrichers/` — `EnricherFn` callable contract + `connection_enricher(store)` factory. May demote to top-level if very small. ~30-50 LOC.
- `select/` — `cel-python` compile + atom-set introspection (Lark Tree walk for atom extraction; strict mode raises `UnknownAtomError` on typos). Reads atoms from FastMCP's tool registry (tags + annotations + `meta["a2kit"]`) at runtime. ~80-100 LOC.
- `formatter/` — Response, Page, Local, Passthrough, **real TOON via `toon-format`** (not the in-house TSV-with-JSON-cells masquerading as TOON), truncate, `format_response`. ~120 LOC.
- `testing/` — pytest fixtures, **syrupy `SingleFileSnapshotExtension` subclass** for per-tool schema snapshots (preserves the byte-count-as-token-budget contract), thin vcrpy glue. ~50 LOC.
- `lint/` — static + runtime + Click CLI (11 files → 2-3 files). Includes new **A2K-DI rules**: flag `Annotated[T, Depends(fn)]` value-injection misuse (uncalled_for treats Annotated as side-effect wrapping, not value injection); flag wrong import paths (`a2kit.di`, `fastmcp.dependencies`); flag non-kwonly DI parameters. ~600 LOC after flatten.

**Console script `a2kit`** dispatches via Click `LazyGroup` to `lint` or `connections` without importing the other. `a2kit --help` lists both without loading fastmcp.

### Deletions (BREAKING — no shims, no deprecation cycle)

| Module | Reason | Replacement |
|---|---|---|
| `di.py` (177 LOC) | uncalled_for canonical pattern is parameter-default `T = Depends(fn)` for value injection; a2kit's `Annotated[T, Depends(fn)]` form was a FastAPI conflation uncalled_for explicitly rejects (issue #3). Migration is mechanical regex sweep. | `from uncalled_for import Depends` — a2kit re-exports nothing |
| `middleware/_chain.py` | FastMCP's `server.add_middleware()` | use FastMCP middleware list |
| `middleware/_logging.py` | `fastmcp.server.middleware.logging` | built-in |
| `middleware/_otel.py` + `_otel.py` | `fastmcp.server.middleware.timing` + OTel SDK direct | built-in + direct |
| `logging.py` (wrapper) | structlog directly | downstream uses structlog |
| `_cassette.py` + schema-snapshot wrappers | vcrpy + syrupy directly | thin fixtures |
| `_select*.py` + `projection.py` | `cel-python` direct + FastMCP tags | `packages/select/` |
| `_capabilities.py` (StrEnum) | maps to FastMCP `tags: set[str]` | tags-based registry in `capabilities.py` |
| `scaffold/` namespace | mislabeled — these are runtime composition primitives | flat top-level `routers.py` / `runner.py` / `cli.py` |
| `contrib/connections/` | `get_conn_factory` is the canonical DI shape, not "contrib" | `packages/connections/` |
| `FastMCPLike` Protocol | hard FastMCP dep makes it pointless | depend on `FastMCP` directly |

### Layout discipline

- Zero `_*.py` modules with public symbols. Inline into parent OR promote to a public name.
- One concept per file, name = concept. No `helpers.py` / `utils.py` / `common.py`.
- Core LOC ≤ 2000 (revised down from 3000 — FastMCP absorbs a lot).
- Core files ≤ 12 at top level.
- Three classes of `__init__.py` allowed: `src/a2kit/__init__.py`, `src/a2kit/packages/__init__.py`, `src/a2kit/packages/<name>/__init__.py`.
- The tree is self-documenting: every filename's purpose readable from the name alone.
- **No re-exports of external library symbols.** a2kit's `__init__.py` exports only what a2kit *owns*. Users import `Depends` from `fastmcp` directly, `ToolAnnotations` from `mcp.types`, `Middleware` from `fastmcp.server.middleware`, `SharedContext` from `uncalled_for`, etc. a2kit is not a convenience facade.

## Capabilities

### New Capabilities

- `thin-core-surface`: Defines the post-refactor public API of `a2kit` after FastMCP becomes a hard dependency. Specifies what a2kit owns (decorators, composition primitives, capability tagging, the seven plugin packages), what it delegates to FastMCP (DI, middleware chain, context primitives, OTel/logging built-ins), and which responsibilities are delegated to other FOSS deps (cel-python for select, syrupy for snapshots, vcrpy for cassettes, optionally pydantic-settings for connections).
- `module-layout-discipline`: Defines the file-organization rules — naming conventions, the core/packages split, `__init__.py` minimization, and the "tree is self-evident without comments" invariant.

### Modified Capabilities

(None — `openspec/specs/` is empty.)

## Impact

- **Hard dependency on FastMCP** added. Transitive: `uncalled_for`, `mcp` (official SDK).
- **Public API**: BREAKING throughout. Every existing import path may change. Notable shifts:
  - `from a2kit.di import Depends` → `from fastmcp import Depends` (a2kit does not re-export it)
  - `Context`, `Middleware`, `ToolAnnotations`, `SharedContext` etc. → import from their owning library, not from `a2kit`
  - `from a2kit import ConnectionStore` → `from a2kit.packages.connections import ConnectionStore`
  - `from a2kit.contrib.connections import get_conn_factory` → `from a2kit.packages.connections import get_conn_factory`
  - `from a2kit.testing import ...` → `from a2kit.packages.testing import ...`
  - `from a2kit.scaffold import Router, MCPRunner, build_cli` → `from a2kit import Router, MCPRunner, build_cli`
  - `--select` syntax migrates to real CEL.
  - `app.dependency_overrides[fn] = fake` → `uncalled_for.SharedContext` + override mechanism (audit T1.6 specifies exact pattern).
- **Dependencies removed**: `[projection]` extra. `cel-python` promotes to required (or `packages/select/`-required).
- **Repo layout**: No uv workspace. Single PyPI artifact. Plugin packages live under `src/a2kit/packages/`, all in the same wheel.
- **Distribution**: Install from GitHub today. PyPI publish is a future change.
- **Versioning**: v1.0 break. No deprecation cycle, no compat shims.
- **Tests**: Mass import-path rewrite. Override pattern migration to FastMCP/uncalled_for.
- **Docs**: README rewritten with Core + Feature packages structure. CHANGELOG ships migration tables (CEL syntax, import paths, override mechanism).
- **Risk**: Hard dep on FastMCP ties release cadence. Mitigated: FastMCP 3.x is mature; `>=3.2,<4` constraint.
