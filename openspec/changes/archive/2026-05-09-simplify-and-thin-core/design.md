## Context

a2kit today is 94 Python files / ~7.9K LOC across `src/` with 43 underscore-prefixed modules. It bundles seven independent sub-systems under one package while marketing itself as "thin." Discovery: a2kit doesn't actually depend on FastMCP — it uses a `FastMCPLike` Protocol. The marketing line is itself slightly false. The skeptical first-time reader closes the tab. That's the failure mode this change exists to prevent.

External adoption is zero. Downstream consumers are three first-party MCPs (`a2db`, `a2atlassian`, `a2web`) that the author controls. The window for breaking changes is now and will not reopen cheaply. Per user direction: break compat freely, ship no shims.

The current code is mostly correct; the problem is **quantity, shape, and packaging**, not behavior.

## Goals / Non-Goals

**Goals:**

- Establish a clean **core / plugin-package** split. Core is the thin runtime API (decorators + DI + composition root); plugins live under `src/a2kit/packages/` and are individually opt-in.
- Replace in-house code with FOSS dependencies wherever the FOSS coverage is sufficient.
- Establish a layout invariant: tree is self-documenting; no file requires a comment to explain its existence.
- Ship a single PyPI artifact (no workspace, no multi-repo).
- Land a v1.0 cut with no deprecation cycle. Every existing import path is up for revision.

**Non-Goals:**

- Rewriting the tool decorator's runtime behavior. Surface stays; internals consolidate and split.
- Replacing FastMCP. a2kit remains structurally agnostic via `FastMCPLike`.
- Backwards compatibility shims. None. Deleted, not deprecated.
- Building new features. Pure subtraction + reorganization + repackaging.
- uv workspace, monorepo, or separate git repo for any sub-feature.

## Decisions

### D0: Take FastMCP as a hard dependency; delete what FastMCP already ships

a2kit currently uses a `FastMCPLike` Protocol to stay structurally agnostic. Investigation: FastMCP 3.2.4 ships full DI (`uncalled_for`-based `Depends`/`Dependency`), full middleware (`on_call_tool` / `on_list_tools` / `on_initialize` etc. + 10 built-in middlewares: authorization, caching, error_handling, logging, ping, rate_limiting, response_limiting, timing, tool_injection), and context primitives (`CurrentContext`, `CurrentFastMCP`, `CurrentHeaders`, `Progress`).

a2kit currently reimplements significant portions of this. Per user direction ("I would not mind having a dependency on fastmcp"), the right move is to **add FastMCP to `dependencies`** and delete a2kit's reinventions:

| In a2kit today | FastMCP equivalent | Outcome |
|---|---|---|
| `di.py` (177 LOC) | `fastmcp.Depends` + `fastmcp.Dependency` | **delete** `di.py`; users import `from fastmcp import Depends` directly (D17: no re-exports) |
| `middleware/_chain.py` (170 LOC) | `server.add_middleware(...)` | **delete** the chain assembler |
| `middleware/_logging.py` | `fastmcp.server.middleware.logging` | **delete** |
| `middleware/_otel.py` + top-level `_otel.py` | `fastmcp.server.middleware.timing` + OTel SDK direct | **delete** both |
| `middleware/_listview.py` | (a2kit-unique) | move to `packages/middlewares/listview.py` |
| `middleware/_guards.py` | (a2kit-unique) | move to `packages/middlewares/guards.py` |
| `middleware/_enricher.py` | (a2kit-unique) | move to `packages/enrichers/` |
| `FastMCPLike` Protocol | (no longer needed) | **delete**; depend on `FastMCP` directly |

a2kit's `@tool` decorator stops assembling a middleware chain at decoration time. It decorates with `@server.tool()` (or its own thin wrapper that calls FastMCP's tool registration) and additionally registers a2kit-unique middlewares via `server.add_middleware(...)`. The decorator's job shrinks to: verb classification, capability tagging, metadata stamping. Estimated ~200-300 LOC, cleanly splittable along signature/metadata/decorator concerns.

**Trade-offs:**
- Hard dep on FastMCP ties release cadence. Minor risk; FastMCP 3.x is mature.
- Lock to FastMCP's idioms (DI marker semantics, override mechanism, middleware hook set).
- Tests migrate from `app.dependency_overrides[fn] = fake` to FastMCP's override mechanism (whatever its surface is — audit T1.6).

**Alternatives considered:**
- Keep `FastMCPLike` and reimplement: rejected — that's the slop we're cutting.
- Take dep but keep our DI: rejected — two DI systems is worse than zero or one.
- Soft dep via optional extra: rejected — DI lives in the hot path; can't be "optional."

### D1: Thin core + plugin packages

After D0, the architecture splits into two zones:

- **Core** (`src/a2kit/*.py`, top level): the runtime API a2kit owns. Slim decorators, composition primitives, exceptions, capabilities. No DI, no middleware chain (FastMCP owns those).
- **Plugins** (`src/a2kit/packages/<name>/`): orthogonal opt-in features. a2kit core works without any of them.

Plugin packages: `connections/`, `enrichers/`, `select/`, `formatter/`, `middlewares/`, `testing/`, `lint/`.

The split is the answer to "what is core?" — literally what's at `ls src/a2kit/*.py`.

### D2: Replace `--select` grammar with cel-python directly

The in-house `_select` / `_select_parse` / `_select_eval` modules implement a custom grammar (`and/or/not` keywords; `tool:foo`, `cap:foo`, `surface.mcp` atoms). The v0.13-phase-5 plan (`todo.md:908`) was always to migrate to **cel-python**; deferred only because grammar divergence required a coordinated user-facing migration. This refactor is the moment.

User-facing grammar moves to real CEL: `&&` / `||` / `!`, atoms become field accesses (`tool.foo`, `cap.foo`, `surface.mcp`). `SelectExpr` Pydantic AST replaced by cel-python's compiled program plus a small introspection helper.

Lives in `packages/select/`.

**Alternatives considered:**
- *Keep `--select`*: rejected — reinvention is the loudest slop tell.
- *jmespath*: rejected — different semantic model; cel-python already a dev dep.
- *Defer again*: rejected — v1.0 break is the cheap window.

### D3: In-house projection module deleted

`projection.py` (CEL via `cel-python`) folds into `packages/select/`. The `[projection]` optional extra disappears; `cel-python` becomes core (or `packages/select/`-required).

### D4: Lint moves to `src/a2kit/packages/lint/` and flattens

Lint is a feature that ships with a2kit, not part of the runtime API. Moving it to `packages/lint/` makes the separation visible: `ls src/a2kit/` shows core + a `packages/` directory, no lint mixed in.

Inside `packages/lint/`, flatten 11 files → 2-3:
- `static.py` — static analyzer (rules + `_ast_helpers.py` folded in)
- `runtime.py` — runtime analyzer
- `cli.py` — Click CLI

Console script remains: `a2kit = "a2kit.packages.lint.cli:main"`. Single wheel; downstream installs unchanged.

The `packages/` subtree is **excluded from the core LOC/file budget.**

**Alternatives considered:** Move out of wheel (breaks downstream installs); workspace + sibling package (rejected per user); separate repo (rejected per user); delete entirely (rules encode real learning).

### D5: `scaffold/` is mislabeled — flatten into core under accurate names

The `scaffold/` package contains runtime composition primitives (`Router`, `RouterRegistry`, `MCPRunner`, `build_cli`, `scope_filter`, `FastMCPLike`), not boilerplate generators. Flatten:

- `scaffold/_routers.py` → `src/a2kit/routers.py`
- `scaffold/_runner.py` → `src/a2kit/runner.py`
- `scaffold/_cli.py` → `src/a2kit/cli.py`
- `scaffold/_stores.py` (scope_filter + filtered/ephemeral store wrappers) → `src/a2kit/packages/connections/`

Delete the `scaffold/` namespace.

### D6: `testing` becomes `packages/testing/`; delete the wrappers

`a2kit.testing` + `_cassette.py` + schema-snapshot wrappers thin to opt-in pytest fixtures + light vcrpy/syrupy glue. Move under `packages/testing/`. Documentation references vcrpy and syrupy directly.

### D7: `connections.py` becomes `packages/connections/` — and the data contract is on the table

`ConnectionStore` is a recurring need across MCPs but **not core to a2kit's identity**. It's a feature. Move under `packages/connections/` so a2kit core is honestly thin without it. The `contrib/connections/` namespace disappears entirely; `get_conn_factory` lives at `packages.connections.get_conn_factory`.

The earlier probe (`todo.md:945-973`) rejected pydantic-settings *given today's lazy-substitution contract*. Per user direction, the contract itself can be revised. Audit T1.2 picks between:

- **Contract A** (status quo, lazy): `${VAR}` regex substitution at API-call time. Implementation = keep today's `tokens.py` (folded into the connections package).
- **Contract B** (eager, pydantic-settings native): typed fields, ENV / `op://` resolved at load time, fail-fast. Implementation = adopt pydantic-settings; tokens shrinks to just an `op://` resolver or disappears.

T1.2 produces a recommendation with worked examples for both before code lands.

### D8: Delete `logging.py` wrapper; do not ship a structlog binder

`todo.md:96` flagged `a2kit.get_tool_logger(name)` as a deferred 200+ LOC rabbit hole. Skip it. The wrapper is deleted; downstream MCPs use structlog directly.

### D9: Delete `_otel.py`

Audit T1.3 confirms it's a pass-through over FastMCP middleware + the OTel SDK. Default outcome: delete. The OTel middleware itself becomes one file in `packages/middlewares/`.

### D10: Split `tool.py` along orthogonal axes

The current `tools/_decorator.py` (421) + `_signature.py` (274) + `_metadata.py` (189) + `_verbs.py` (141) + `_connection.py` + `_runtime.py` is one large concept ("the fat tool decorator") but breaks cleanly along three orthogonal axes:

- `tool.py` — the public decorator family (`@tool`, `@read`, `@write`, `@list`) + verb behavior. Calls into `signature.py` and `metadata.py`.
- `signature.py` — Annotated/Depends extraction, kwonly inspection, type hint resolution.
- `metadata.py` — `ToolMetadata`, the WeakKeyDictionary registry, `tool_metadata(fn)`.

Three sibling top-level files. No `tools/` subpackage.

**Alternative considered:** one ~1100-LOC `tool.py`. Rejected — the orthogonal split improves legibility without artificial seams. (Trade-off: 3 files instead of 1, but each name is self-evident.)

### D11: `middleware.py` (chain protocol) in core; concrete middlewares as `packages/middlewares/`

The middleware chain assembler is part of how `@tool` works — not optional. Stays in core as `middleware.py` (or rename to `chain.py` for clarity; decided post-implementation).

The concrete middlewares (otel, listview, guards) are individually opt-in via `app.use(...)`. Each becomes one file under `packages/middlewares/`:
- `packages/middlewares/otel.py`
- `packages/middlewares/listview.py`
- `packages/middlewares/guards.py`

The current `_logging.py` middleware deletes per D8. The current `_enricher.py` middleware moves to `packages/enrichers/` (it's the enricher implementation).

### D12: Underscore-prefix elimination

A file is either:
- **Inlined** into its parent module (most `_*.py` cases — they are slices of one concept), or
- **Public** (`name.py`, exported from `__init__.py`) — no underscore prefix.

`__init__.py` excepted. No third option.

### D13: One concept per file, name = concept

Every file in `src/a2kit/` answers "what is this?" by its name alone. If a name needs a docstring to explain it, the name is wrong. No `helpers.py`, `utils.py`, `common.py`, `_helpers.py`, `_utils.py`, `_common.py` anywhere.

### D14: `__init__.py` minimization

Allowed `__init__.py` files (post-refactor target = 9):
- `src/a2kit/__init__.py` (core re-export surface)
- `src/a2kit/packages/__init__.py` (namespace only)
- `src/a2kit/packages/<name>/__init__.py` × 7 (one per plugin package)

No subpackage `__init__.py` re-exports underscore-prefixed siblings. Public files only.

`tools/`, `middleware/`, `contrib/` subpackages disappear (D5, D7, D10, D11).

### D15: Demotion rule for tiny plugin packages

If `enrichers/` or `select/` ends up below ~50 LOC of source after simplification, demote to a top-level file (`enrichers.py` / `select.py`) at the core boundary. Plugin-shape signals orthogonality, not file count; a 30-LOC package is silly.

Decided post-implementation when LOC numbers are real.

### D16: No backwards compatibility

Per user direction: every v0.x compat shim is deleted. No deprecation cycle. No `module-level alias for one cycle` pattern. Imports break; downstream MCPs migrate in lockstep. This is the v1.0 break.

### D17: a2kit re-exports nothing from external libraries

a2kit's public surface (the top-level `a2kit/__init__.py` and every plugin package's `__init__.py`) SHALL contain **only symbols a2kit defines**. External library symbols are imported by users directly from the owning library:

- `Depends`, `Dependency`, `Shared`, `SharedContext`, `Context` → `from fastmcp import ...` (or `from uncalled_for import ...` for the lower-level pieces)
- `Middleware` (base class) → `from fastmcp.server.middleware import Middleware`
- `ToolAnnotations` → `from mcp.types import ToolAnnotations`
- structlog, OTel SDK, cel-python, vcrpy, syrupy types → import from their own libraries

This kills the "convenience facade" slop pattern. When a user opens `a2kit/__init__.py`, every name they see is something a2kit *owns* — no aliased imports from upstream. Plugin packages follow the same rule.

**Rationale**: re-exports look thin (one file with `from x import y; from x import z`) but they grow the perceived surface area, hide upstream changes, and make ownership ambiguous. Users learning the ecosystem benefit from knowing where each primitive comes from.

### D-P3: protocol-agnostic core; FastMCP isolated in `packages/mcp/` ✅ LOCKED

User-confirmed direction. The `@tool` decorator stamps protocol-neutral metadata onto functions; the FastMCP adapter lives at `packages/mcp/` and is the only place fastmcp is imported.

**Adapter pattern verified (Round-5 Probe I):**

```python
# Pre-decoration (a2kit core, no fastmcp):
async def list_tasks(project_id: str | None = None) -> list[Task]:
    ...
list_tasks._a2kit = {"verb": "list", "tags": {"read"}, ...}

# Adapter time (packages/mcp/server.py, fastmcp loads here):
from fastmcp.tools.function_tool import FunctionTool
tool = FunctionTool.from_function(
    list_tasks,
    name="list_tasks",
    tags=list_tasks._a2kit["tags"],
    annotations=ToolAnnotations(readOnlyHint=True),
    meta={"a2kit": {...}},
)
server.add_tool(tool)
```

Tags, annotations, and `tool.meta["a2kit"]` round-trip correctly; tool calls execute. Verified end-to-end.

**User entry pattern (recommended — two-file split):**

- `app.py` — builds the `App` registry. No fastmcp, no click. Just `a2kit.App` + `app.connect()` + `app.use(Router)`.
- `mcp_server.py` — `from .app import app; from a2kit.packages.mcp import build_mcp_server; server = build_mcp_server(app)`. Used by `fastmcp run mcp_server.py`.
- `cli.py` — `from .app import app; from a2kit.packages.cli import build_cli; build_cli(app)()`. Used as `python -m yourpkg.cli`.

The CLI path never imports fastmcp. Sub-second cold-start.

### D-DI-Convention: adopt uncalled_for canonical pattern; drop a2kit's di.py ✅ LOCKED

User-confirmed direction. uncalled_for explicitly separates two concerns by syntax:
- `param: T = Depends(fn)` — value injection (default form)
- `Annotated[T, Dep()]` — side-effect wrapping (rate limits, validators, admission control)

a2kit's existing `Annotated[T, Depends(fn)]` for value injection is the FastAPI conflation. uncalled_for considers the conflation a design flaw (verified in their issue #3 closing notes).

**Migration:** every tool fn signature changes from `*, conn: Annotated[Conn, Depends(get_conn)]` to `*, conn: Conn = Depends(get_conn)`. Mechanical sed sweep:

```
Annotated\[(\w+), Depends\((\w+)\)\] → \1 = Depends(\2)
```

**Saves ~177 LOC** (the entire `di.py`). Plus a2kit gains uncalled_for's Annotated side-effect form for free — usable later for admission control / validators (e.g. `Annotated[str, ProjectExists()]`).

**Lint rule (added — A2K-DI):** flag `Annotated[T, Depends(fn)]` in tool signatures with the message: *"uncalled_for treats Annotated `Depends` as side-effect wrapping (no value injection). For value injection, use parameter-default form: `T = Depends(fn)`."* Static rule, runs in `packages/lint/static.py`. Catches the bug class permanently.

Plus secondary DI lint rules:
- A2K-DI-IMPORT: flag `from a2kit.di import Depends` (legacy) and `from fastmcp.dependencies import Depends` (slow). Recommend `from uncalled_for import Depends`.
- A2K-DI-KWONLY: flag tool fns with non-kwonly DI parameters (a2kit requires kwonly).

### D-Single-Entry: `a2kit.run(app)` is the canonical user entry ✅ LOCKED

User-stated requirement: "one entry-point, hidden in a2kit, integration surface thin." Tool authors install via `uvx`; the package has one console script that dispatches all modes (CLI tool calls, connection management, MCP serve) based on argv.

**User pattern (the only file authors write):**

```python
# tracker/server.py
import a2kit
from .routers import ProjectsRouter, TasksRouter
from .connection import TrackerConn

app = a2kit.App("tracker")
app.connect(TrackerConn)
app.use(ProjectsRouter)
app.use(TasksRouter)

def main() -> None:
    a2kit.run(app)
```

```toml
# tracker/pyproject.toml
[project.scripts]
tracker = "tracker.server:main"
```

**Invocations:**

```
$ uvx tracker --help                       # ~150ms (click + a2kit core only)
$ uvx tracker connections login prod ...   # ~500ms (+ pydantic-settings + tomli)
$ uvx tracker tasks list-tasks --conn=prod # ~500ms (in-process; no fastmcp)
$ uvx tracker serve [--stdio | --http :8080]  # ~3.7s (fastmcp loads here)
```

**Internal dispatcher** (`a2kit.packages.cli.build_full_cli`):

- Click `_LazyGroup` at top level.
- Subcommands eager (no fastmcp): one per registered Router (with progressive-disclosure hints), `connections` group.
- Subcommand lazy (loads fastmcp only when invoked): `serve` lives in `a2kit.packages.mcp.cli` and is registered via `LazyGroup.lazy_subcommands={"serve": ("a2kit.packages.mcp.cli", "serve_command")}`.
- The user's `App` is passed to `serve_command` via a ContextVar set by `build_full_cli` before dispatch (Click closure trick).

**Cold-start ladder per invocation:**

| Command | Loads | Time |
|---|---|---|
| `tracker --help` | click + a2kit core | ~150ms |
| `tracker tasks list-tasks ...` | + uncalled_for + pydantic + tool module | ~500ms |
| `tracker connections login ...` | + pydantic-settings + tomli | ~500ms |
| `tracker serve --stdio` | + fastmcp | ~3.7s |

**Kills these from the design:**
- `App.run` / `App.run_server` / `App.run_async` — deleted. Single `a2kit.run(app)` covers all.
- The earlier "user writes three entry files" (app.py / mcp_server.py / cli.py) — deleted. One file, one `main()`.
- Reliance on `fastmcp run server.py` discovery — deleted. a2kit owns its `serve` subcommand.

**`App` shrinks to ~50 LOC**: `name`, `_routers`, `_stores`, `connect(ConnT)`, `use(Router)`, `get_store(ConnT)`. No method that touches FastMCP, no `.run()`. Borderline-dataclass; downgrade if implementation reveals it doesn't earn its method surface.

### D-Schema-Discovery: tool schemas exposed via CLI without fastmcp ✅ NEW

User-stated requirement. LLM-as-CLI-consumer and CI snapshot contracts both need tool schemas. Two surfaces:

**1. Per-tool `--schema` flag** — on every tool subcommand. Prints the full MCP-shaped schema (`name`, `description`, `inputSchema`, `outputSchema`, `annotations`, `tags`, `meta`) as JSON.

**2. Top-level `schema` command** — batch + filter:
- `tracker schema` — all tools as `{name: schema}` JSON object
- `tracker schema create_task` — one tool
- `tracker schema --jsonl` — newline-delimited (pipeable)

**Implementation (`packages/cli/schemas.py`):** pydantic generates JSON schemas from type hints natively. `uncalled_for.without_dependencies(fn)` strips DI params before introspection. ~50 LOC. **No fastmcp loaded.**

```python
def compute_schema(fn) -> dict:
    from uncalled_for import without_dependencies
    user_fn = without_dependencies(fn)
    sig = inspect.signature(user_fn)
    hints = typing.get_type_hints(user_fn)
    fields = {n: (hints[n], p.default) for n, p in sig.parameters.items()}
    InputModel = pydantic.create_model(f"{fn.__name__}_Input", **fields)
    return_anno = hints.get("return")
    return {
        "name": fn._a2kit["tool_name"],
        "description": (fn.__doc__ or "").strip(),
        "annotations": dataclasses.asdict(fn._a2kit["annotations"]),
        "tags": sorted(fn._a2kit["tags"]),
        "inputSchema": InputModel.model_json_schema(),
        "outputSchema": pydantic.TypeAdapter(return_anno).json_schema() if return_anno else None,
        "meta": {"a2kit": fn._a2kit.get("meta", {})},
    }
```

**Reused by `packages/testing/`** for the per-tool snapshot contract: syrupy `SingleFileSnapshotExtension` calls `compute_schema(fn)` and writes one `<tool>.json` per tool. Byte size = token-budget proxy. Same helper powers schema-drift detection in CI.

**Cold-start path:**

```
tracker schema → click + pydantic + uncalled_for + tool module = ~500ms
```

LLMs/agents/CI can introspect the entire tool surface without speaking MCP, without spawning a server, without loading fastmcp.

### D-CLI-Disclosure: progressive disclosure via Click nested groups by Router ✅ NEW

User-stated requirement. The CLI for an MCP author's `App` exposes:

```
$ tracker
Usage: tracker [OPTIONS] COMMAND [ARGS]...

  Tracker MCP — manage projects and tasks.

Commands:
  connections  Manage stored connection configurations.
  projects     Project-scoped tools. (run `tracker projects` for tools)
  tasks        Task-scoped tools. (run `tracker tasks` for tools)

$ tracker tasks
Usage: tracker tasks [OPTIONS] COMMAND [ARGS]...

  Task-scoped tools.

Commands:
  list-tasks     List tasks, optionally narrowed to one project.
  get-task       Fetch one task by id.
  create-task    Create a task under <project_id>.
  complete-task  Mark a task done. Idempotent.
```

**Implementation in `packages/cli/`:**
- `build_cli(app)` returns a Click group.
- Top-level group has one Click subgroup per registered Router (slug = `Router.__name__` lowercased / underscored — same as today's auto-slug).
- Each Router subgroup has one subcommand per registered tool. Subcommand name = tool name (kebab-cased: `list_tasks` → `list-tasks`).
- Tool subcommand args = the tool's kwonly parameters (excluding DI deps, which `without_dependencies(fn)` strips). Click `--connection`, `--project-id`, etc. mapped from kwargs.
- Tool subcommand body = `await without_dependencies(fn)(**user_kwargs)` — uncalled_for resolves the Depends chain at invocation; tool runs in-process.
- Plus a `connections` Click group from a2kit (login/logout/list/show/delete).
- Each Router-group's `help` text includes a hint: *"(run `<app> <router>` for tools)"*.

**Cold-start path:** `tracker tasks list-tasks --connection prod --project-id 42`:
1. Click parses argv (40ms).
2. uncalled_for resolves Depends chain (~71ms + connection load).
3. pydantic validates tool kwargs (~50ms).
4. tool body runs.

Total: < 500ms cold for typical tools. **No fastmcp loaded.**

**Click LazyGroup pattern** for `a2kit` console script (lint vs connections subgroups):

```python
class LazyGroup(click.Group):
    def __init__(self, *args, lazy_subcommands=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}
    def list_commands(self, ctx):
        return sorted(super().list_commands(ctx) + list(self.lazy_subcommands))
    def get_command(self, ctx, name):
        if name in self.lazy_subcommands:
            mod, attr = self.lazy_subcommands[name]
            from importlib import import_module
            return getattr(import_module(mod), attr)
        return super().get_command(ctx, name)

@click.command(cls=LazyGroup, lazy_subcommands={
    "lint":        ("a2kit.packages.lint.cli", "main"),
    "connections": ("a2kit.packages.connections.cli", "main"),
})
def main(): pass
```

`a2kit --help` lists subcommands without importing them. `a2kit lint <files>` imports only `a2kit.packages.lint.cli` (no fastmcp). Same for `a2kit connections`.

### D-Cold-Start: import discipline keeps CLI invocations fast

FastMCP's full import is **6.8s cold / 3.6s warm** (verified in F2). For any CLI invocation that doesn't need the runtime layer (lint, connection management), paying that cost is unacceptable.

**Discipline rules (enforced by CI):**

1. **`src/a2kit/__init__.py` uses PEP 562 `__getattr__`** for lazy attribute resolution:
   ```python
   _LAZY_ATTRS = {
       "App": ("a2kit.app", "App"),
       "Router": ("a2kit.routers", "Router"),
       "RouterRegistry": ("a2kit.routers", "RouterRegistry"),
       "MCPRunner": ("a2kit.runner", "MCPRunner"),
       "tool": ("a2kit.tool", "tool"),
       "read": ("a2kit.tool", "read"),
       "write": ("a2kit.tool", "write"),
       "list_": ("a2kit.tool", "list_"),  # `list` collides with builtin; underscore-suffix per PEP 8
       # ...
   }

   def __getattr__(name: str):
       if name in _LAZY_ATTRS:
           mod_name, attr = _LAZY_ATTRS[name]
           import importlib
           return getattr(importlib.import_module(mod_name), attr)
       raise AttributeError(f"module 'a2kit' has no attribute {name!r}")
   ```
   `import a2kit` triggers no fastmcp import. `a2kit.App(...)` triggers `a2kit.app` import which loads fastmcp (~3.6s) — unavoidable when actually using the runtime.

2. **`src/a2kit/__main__.py`** is the `a2kit` console script entry. Pure stdlib + `sys.argv` peek. Dispatches to lint or connections subgroups by importing the relevant subpackage CLI module only when chosen:
   ```python
   def main() -> None:
       import sys
       sub = sys.argv[1] if len(sys.argv) > 1 else None
       if sub == "lint":
           from a2kit.packages.lint.cli import main as lint_main
           lint_main()
       elif sub == "connections":
           from a2kit.packages.connections.cli import main as conn_main
           conn_main()
       else:
           _print_help()  # no imports
   ```
   Console script: `a2kit = "a2kit.__main__:main"`.

3. **Fastmcp-free zones (enforced by lint rule):**
   - `src/a2kit/__init__.py` — top-level imports must not chain to fastmcp.
   - `src/a2kit/__main__.py` — same.
   - `src/a2kit/packages/lint/**` — static analyzer, AST + Click only.
   - `src/a2kit/packages/connections/**` — connection management is a CLI concern; only pydantic + pydantic-settings + tomli-w + structlog (optional). NO fastmcp.
   - `src/a2kit/packages/formatter/**` — TOON encoding + truncation; pydantic + toon-format only.
   - `src/a2kit/capabilities.py`, `exceptions.py`, `signature.py` — pure stdlib + typing.

4. **Fastmcp-allowed zones:**
   - `src/a2kit/app.py`, `tool.py`, `routers.py`, `runner.py` — runtime layer; loads fastmcp by design.
   - `src/a2kit/packages/middlewares/**` — subclass `fastmcp.server.middleware.Middleware`.
   - `src/a2kit/packages/enrichers/middleware.py` — same.
   - `src/a2kit/packages/select/**` — reads `server.list_tools()` at runtime.
   - `src/a2kit/packages/testing/**` — test-time only.

5. **CI guarantees (added):**
   - `time python -c 'import a2kit'` < 100ms.
   - `time python -c 'import a2kit.packages.lint.cli'` < 300ms.
   - `time python -c 'import a2kit.packages.connections.cli'` < 500ms.
   - `python -c "import a2kit.packages.lint.cli; import sys; assert 'fastmcp' not in sys.modules"` passes.
   - `python -c "import a2kit.packages.connections.cli; import sys; assert 'fastmcp' not in sys.modules"` passes.

6. **Per-tool CLI subcommand generation deleted.** `App._build_cli()` lines 219-256 (auto-generating Click subcommands for every registered tool) is removed. `fastmcp call <server> <tool> <kwargs>` covers the same use case.

### D18: Two new specs, no modified specs

`openspec/specs/` is empty (verified). New: `thin-core-surface` (the post-refactor public API contract) and `module-layout-discipline` (the file-layout invariant).

## Risks / Trade-offs

- **[Every downstream import path breaks]** → Mitigation: this is a coordinated v1.0 break; downstream MCPs migrate in the same PR cycle. Per user direction, we don't pay for compat.
- **[CEL grammar migration breaks every memorized `--select`]** → Mitigation: translation table + worked examples in CHANGELOG; optional migration script if call-site audit shows it pays off.
- **[`SelectExpr` introspection callers (`validate_atoms`)]** → Mitigation: T1.1 inventories every introspection site; replace with cel-python AST walk OR thin compile+inspect helper.
- **[Contract A vs B coin-flip in connections]** → Mitigation: T1.2 produces recommendation with worked examples for both before code lands.
- **[Plugin packages become micro-packages]** → Mitigation: D15 demotion rule. Real LOC numbers decide; symmetry doesn't override common sense.
- **[Lint flatten loses a rule by accident]** → Mitigation: flatten one rule-file at a time; run lint test suite after each merge.
- **[Three-file tool decorator split feels gratuitous]** → Mitigation: each split file is named for an orthogonal concern (decoration vs signature vs metadata); reader can locate logic by name.

## Migration Plan

Single phase. One long-lived branch (`v1-thin-core`). One merge.

### Audits (block implementation)

1. **T1.1** — Inventory every `--select` expression across `a2db`, `a2atlassian`, `a2web`, `examples/`, and `default_select` strings. Build legacy-atom → CEL translation table.
2. **T1.2** — Decide Contract A vs B for connections. Worked examples for both. Recommendation lands in this design's "Open Questions" section before code starts.
3. **T1.3** — Confirm `_otel.py` and `logging.py` are pass-throughs. Default = delete.
4. **T1.4** — Audit `formatter.py`. Identify TOON-essential vs generic utility cruft.
5. **T1.5** — Confirm vcrpy + syrupy can replace `_cassette.py` + schema-snapshot wrappers entirely.

### Implementation (after audits)

6. **CEL migration**: promote `cel-python` to required dep; build `packages/select/`; migrate every legacy expression; delete `_select*` + `projection.py`; ship CHANGELOG translation recipe.
7. **Connections package**: build `packages/connections/` per Contract A or B. Absorb `tokens.py` (or shrink it). Move `get_conn_factory` from `contrib/`. Move `_stores.py` from `scaffold/`. Delete `contrib/`.
8. **Scaffold flatten**: `scaffold/_routers.py` → `routers.py`; `_runner.py` → `runner.py`; `_cli.py` → `cli.py`. Delete `scaffold/`.
9. **Tool split**: `tools/_decorator.py` + `_signature.py` + `_metadata.py` + `_verbs.py` + `_connection.py` + `_runtime.py` → top-level `tool.py` + `signature.py` + `metadata.py`. Delete `tools/`.
10. **Middleware split**: chain assembler stays in core as `middleware.py` (or `chain.py`). Concrete middlewares → `packages/middlewares/{otel,listview,guards}.py`. `_enricher.py` → `packages/enrichers/`. `_logging.py` deleted (D8).
11. **Formatter package**: `formatter.py` → `packages/formatter/` (internal split or single file decided by T1.4).
12. **Testing package**: `testing.py` + `pytest_plugin.py` → `packages/testing/`. Delete `_cassette.py`.
13. **Lint flatten**: `lint/` → `packages/lint/` with `static.py` + `runtime.py` + `cli.py`. Update console script to `a2kit.packages.lint.cli:main`.
14. **Delete observability wrappers**: `_otel.py`, `logging.py`. Downstream uses structlog directly.
15. **Underscore sweep**: every remaining `_*.py` (non-`__init__`) inlined or promoted. Verify zero matches.
16. **Comment sweep**: strip comments that paraphrase code. Keep only non-obvious-why.
17. **README rewrite**: surface table organized as Core + Feature packages. Single screen.
18. **Examples rewrite**: against the new shape. Delete examples that exercised removed primitives.
19. **CHANGELOG**: v1.0 break notes + CEL translation recipe + import-path migration table.
20. **Tests green** end-to-end.
21. **Tag `v1.0.0-rc1`**, ship to downstream MCPs for migration.

### Downstream migration

22. `a2db`, `a2atlassian`, `a2web` migrate to v1.0-rc1: CEL syntax, new import paths, structlog direct. Each greens.
23. Tag `a2kit` v1.0.0 final. Publish to PyPI (or stay GitHub-install for now per user — out of scope).

### Rollback

Single merge commit on `v1-thin-core`. Revert if downstream migration surfaces a blocker.

## Open Questions

- T1.1: legacy-atom → CEL translation table (`tool:foo`, `cap:foo`, `surface.mcp`, `_atom_polarity`/`_expr_mentions` introspection). **Status: TBD — partial coverage possible from `a2kit` only; full coverage requires `a2db`/`a2atlassian`/`a2web` checkouts.**
- D11: rename `middleware.py` → `chain.py`? **Status: MOOT** — D0 (FastMCP-as-dep) deletes the chain assembler entirely. No `middleware.py` in core.
- D15: which plugin packages demote to top-level files? **Status: deferred to implementation** — decided when real LOC numbers land.
- `docs.py` fate: **Status: deferred to T13.8** (audit during implementation).

## Audit Findings — landed 2026-05-09

### T1.3 — OTel + logging wrapper audit ✅

**Files audited:** `_otel.py` (118 LOC), `logging.py` (74 LOC), `middleware/_otel.py` (91 LOC), `middleware/_logging.py` (53 LOC). Total: ~336 LOC.

**Finding:** Not pass-throughs. The wrappers add real semantics:
- Auto-stamp `tool.name` / `tool.connection` / `tool.write` on every span without caller threading them.
- Bridge OTel spans ↔ structlog contextvars under the same key names (`tool.*`).
- Stamp `tool.result.count` cardinality after success (PII-safe).
- `plugin_span(name)` for plugin authors to open child spans.

**However**, FastMCP 3.x has `Tool.get_span_attributes()` and ships native middleware (`fastmcp.server.middleware.timing`). The bindings can be re-expressed as one slim FastMCP middleware that:
- Subclasses `fastmcp.server.middleware.Middleware`, hooks `on_call_tool`.
- Reads `tool.meta["a2kit"]` for connection key (stamped at decoration time per T1.7).
- Opens an OTel span using the OTel SDK directly (no `_OTelWrapper`).
- Optionally binds structlog contextvars for the call duration.
- Stamps `tool.result.count` after success.

**Recommendation: DELETE all four files.** Build one `packages/middlewares/observability.py` (~50-70 LOC). Net ~85% reduction. Make it opt-in via `app.use(ObservabilityMiddleware())`. `plugin_span` use case (plugins opening child spans) — plugin authors call `opentelemetry.trace.get_tracer("a2kit")` directly; we don't ship a helper.

### T1.4 — Formatter audit ✅

**File audited:** `formatter.py` (446 LOC).

**Functional breakdown:**
| Concern | LOC | Category |
|---|---|---|
| `truncate()` recursive string clipper | ~16 | Generic — could be inline |
| TSV/TOON tabular encoder (`_is_uniform_row_list`, `_has_nested_values`, `_encode_row_cell`, `_tabular_encode`) | ~35 | TOON-specific |
| Pydantic flat-fields decision (`_flat_pydantic_fields`, `_classify_arm`) | ~50 | TOON-specific |
| `format_from_annotation` + helpers (`_unwrap_awaitable`, `_is_mapping_origin`, `_is_typed_dict`, `_list_format_from_item`) | ~95 | TOON-decision-specific |
| `_dump_items` Pydantic→dict normalization | ~24 | TOON-specific |
| `toon_or_json` wire-format entry point | ~19 | TOON-specific |
| `Response`, `Page`, `ListViewMode`, `Local`, `Passthrough` | ~45 | Public types |
| `format_response` orchestrator + `_encode` + `_apply_filter_and_fields` | ~50 | Glue (calls projection.py — DEAD after CEL migration) |

**Finding:** TOON is genuinely load-bearing — agents get tabular data at ~50% JSON byte count. Cannot delete. `_apply_filter_and_fields` calls `a2kit.projection` which is being deleted; that section moves to use cel-python directly (or moves into `packages/select/`).

**Recommendation: 3-file split inside `packages/formatter/`:**
- `response.py` (~50 LOC) — `Response`, `Page`, `ListViewMode`, `Local`, `Passthrough` types.
- `toon.py` (~220 LOC) — TSV/TOON encoder + Pydantic flat-fields decision + `format_from_annotation` + `toon_or_json` + `_dump_items`.
- `__init__.py` (~50 LOC) — `format_response` orchestrator + `truncate` (inline 16 LOC) + public re-exports of own symbols.

Total: ~320 LOC across 3 files (down from 446 — duplication purged + projection-dependent code reworked). `truncate.py` not separate; folded into `__init__.py`.

### T1.5 — vcrpy + syrupy direct-replacement audit ✅

**Files audited:** `_cassette.py` (49 LOC), `testing.py` (151 LOC).

**Findings:**
- **`_cassette.cassette()`** is a 5-line wrapper: missing cassette → `record_mode="once"`; existing → `"none"`. **Replaceable with a 5-line pytest fixture or doc.**
- **`testing.snapshot_schemas` + `assert_schemas_match`** are bespoke. They write one JSON file per tool because `os.path.getsize()` is the token-budget proxy contract — drift detection AND budget assertion in one artefact. **Syrupy does not replace this.** Syrupy serializes one snapshot file per test, not per tool, and doesn't expose per-snapshot byte counts as the assertion target. Keep.
- `testing._list_tools` accesses `server._tool_manager.list_tools()` — replaceable with FastMCP's `await server.list_tools()` (verified in T1.8 probe).

**Recommendation:**
- DELETE `_cassette.py`. Document `vcrpy` direct usage in `packages/testing/`'s docstring.
- KEEP `snapshot_schemas` / `assert_schemas_match` — move to `packages/testing/snapshots.py` (~80 LOC after cleanup, switching from `_tool_manager.list_tools()` to `await server.list_tools()`).
- Add ~5-line `cassette` fixture in `packages/testing/__init__.py` for users who want the policy preserved.

Net: ~200 LOC → ~90 LOC.

### T1.6 — FastMCP / uncalled_for override mechanism ✅

**Probe finding:** `uncalled_for` exposes `Shared`, `SharedContext`, `resolved_dependencies`, `without_dependencies`, `validate_dependencies`. There is **no `dependency_overrides` dict on the FastMCP server**.

**Override patterns available:**
1. **`Shared` factory replacement at construction time**: when registering a `Shared` dependency, the test fixture builds a server that uses a fake factory. No runtime swap.
2. **`SharedContext.resolved` ContextVar pre-population**: enter `SharedContext()`, populate the `resolved: dict[factory, value]` ContextVar with fakes before exercising the code. Works mid-test.
3. **`without_dependencies(fn)`**: bypass DI on a specific function call; pass kwargs manually.

**For a2kit's `app.dependency_overrides[get_conn] = fake_conn` pattern**, the cleanest replacement is **construction-time replacement**: a2kit's `App.connect(ConnT, *, factory=None)` accepts an optional factory override. Tests build their app with `App.connect(TrackerConn, factory=fake_get_conn)`. No runtime override-map abstraction.

**Recommendation:** **`packages/testing/` ships no override-map abstraction.** Tests use `App(connections=[...], overrides={ConnT: fake})` shape, where `overrides` is a kwarg on `App.__init__` that wires fake factories at construction. ~5-line helper if any. Document the `SharedContext` pattern as the escape hatch for advanced cases.

### T1.7 — FastMCP middleware integration ✅

**Probe finding:** `fastmcp.server.middleware.Middleware` is async-class-based. Hooks: `on_message` → `on_request`/`on_notification` → method-specific (`on_call_tool`, `on_list_tools`, etc.). `MiddlewareContext` has `.method`, `.type`, `.message`. `CallNext` advances the chain. Registered via `server.add_middleware(MyMiddleware())` or `FastMCP(middleware=[...])`.

**Files audited:** `middleware/_listview.py` (57 LOC), `middleware/_guards.py` (60 LOC), `middleware/_enricher.py` (39 LOC).

**Mapping (1:1 verified):**
| a2kit today | FastMCP shape |
|---|---|
| `list_view_apply_factory()` (filter/fields/pagination + stream drain) | `class ListViewMiddleware(Middleware): async def on_call_tool(self, ctx, call_next): ...` |
| `tool_call_guard` (kwarg shape detection) | `class ToolCallGuardMiddleware(Middleware): async def on_call_tool(...)` |
| `enrich_errors_factory(enricher)` | `class EnricherMiddleware(Middleware): async def on_call_tool(...)` |
| `capability_guard` (placeholder, no behavior) | DELETE |

**Decoration-time settings location**: a2kit currently uses `ctx.state["lv_settings"]`. FastMCP's `Tool` has a `.meta: dict` field (verified in probe — `Tool.attrs` includes `meta`, `get_meta`). **Stamp a2kit decoration-time data into `tool.meta["a2kit"]`** at registration; middlewares read it from there.

**Recommendation:** Move all three middlewares to `packages/middlewares/` as concrete `Middleware` subclasses. Each becomes one file, ~30-60 LOC. `capability_guard` deletes. Decoration-time data lives in `Tool.meta["a2kit"]`. **No behavior loss.**

### T1.8 — FastMCP tags-based filtering ✅

**Probe finding (verified):** FastMCP `Tool` instances expose `tags: set[str]` and `annotations: ToolAnnotations(readOnlyHint=..., destructiveHint=..., ...)`. `await server.list_tools()` returns `list[Tool]`. Tags survive registration round-trip:

```python
@server.tool(tags={"read", "demo"}, annotations={"readOnlyHint": True})
def hello() -> str: ...
# tool.tags == {'read', 'demo'}; tool.annotations.readOnlyHint == True
```

**For `--select` evaluation:**
- a2kit's `Cap` StrEnum values become FastMCP tag strings.
- The `--select` evaluator iterates `await server.list_tools()`, builds an evaluation context per tool from `(tags, annotations, meta)`, runs the cel-python compiled program, returns the filtered set.
- Filtering happens server-side in the runner before tools are exposed (same lifecycle as today, different source).

**No parallel metadata store needed.** `Tool.meta["a2kit"]` carries any a2kit-only data not in tags/annotations (e.g. router slug, list-view settings).

**Recommendation:** `packages/select/` reads from FastMCP's tool registry directly. The capability registry shrinks to a thin convention (Cap → string mapping + atom-set introspection helper for cel-python's `validate_atoms` parity). Estimated ~80-100 LOC.

### T1.2 — Connections data contract (Contract A vs B) ✅

**Files audited:** `connections.py` (364 LOC), `tokens.py` (123 LOC).

**Contract A (status quo, lazy):** Field stores literal `prefix-${TOKEN}-suffix`. `tokens.resolve_token(value)` is called at API-call time (lazy). Failures surface at first tool call. `tokens.py` provides `ResolverRegistry` with `op://` + `${ENV}` + literal-fallback rules; pluggable.

**Contract B (eager, pydantic-settings native):** Fields are typed; ENV / `op://` resolved at construct time. Failures surface at startup.

**Probe outcome (extends `todo.md:945-973`):**

1. **`pydantic-settings` does not natively cover `${VAR}` substitution inside arbitrary string fields.** Its model is "load this field from `OS_ENV_VAR_NAME`," not "substitute `${VAR}` patterns inside literal strings." Adopting it requires a `SettingsConfigDict(env_nested_delimiter=...)` + custom validator OR a custom `pydantic_settings.PydanticBaseSettingsSource`. Doable, but it's a custom source either way — not a straight win.

2. **`pyonepassword` saves ~15 LOC at the cost of two transitive deps.** Same finding as `todo.md:957-963`. Not worth it.

3. **`tokens.py`'s pluggable `ResolverRegistry` is genuinely useful** — downstream MCPs can register additional resolvers (e.g., `vault://`, `aws-sm://`) without forking `tokens.py`. Contract B loses this unless we still ship a Settings source layer that re-creates the registry concept.

4. **The lazy-vs-eager trade-off is real:** lazy lets env vars be set after process start; eager fails fast at startup. For MCPs (long-lived processes started with full env), eager is *probably* better, but the difference is ergonomic, not architectural.

**Recommendation: STAY ON CONTRACT A.** Reasons:
- pydantic-settings doesn't cleanly cover the `${VAR}-inside-string` shape; we'd write a custom Settings source either way (no LOC saved).
- The pluggable resolver registry has external-MCP value (vault://, aws-sm://, etc.) and would have to be rebuilt under Contract B.
- Lazy resolution preserves "fix env, restart agent, no code change" debugging ergonomics.
- `tokens.py` (123 LOC) is genuinely small and self-contained; folding it into `packages/connections/tokens.py` keeps total LOC low.

**Implementation shape for `packages/connections/`:**
- `store.py` (~200 LOC) — `ConnectionStore` save/load/delete/list. Sliced from current `connections.py` after dead-code audit.
- `config.py` (~100 LOC) — `ConnectionConfig` base + key NamedTuple machinery + `_DefaultKey`. Sliced from current `connections.py`.
- `tokens.py` (~120 LOC) — current `tokens.py`, untouched.
- `factory.py` (~60 LOC) — `get_conn_factory(app, ConnT)` + `connection_enricher(store)` factory. Imported from `contrib/connections/`.
- `filters.py` (~50 LOC) — `scope_filter` + `_EphemeralAwareStore` + `_FilteredStore` from `scaffold/_stores.py`.
- `__init__.py` (~30 LOC) — public re-exports of own symbols.

Total: ~560 LOC across 6 files. Larger than core file budget but acceptable inside a plugin package.

### T1.1 — `--select` expression inventory (PARTIAL) ⚠️

**Coverage:** a2kit-internal only. Downstream MCPs (`a2db`, `a2atlassian`, `a2web`) require their own checkouts; not available in this audit.

**a2kit-internal expressions found** (sampled from grep over `examples/`, `tests/`, `default_select`, `_select*.py`):

| Form | Count | CEL equivalent |
|---|---|---|
| `default and not write` | many | `default && !write` |
| `default and not write and surface.mcp` | many | `default && !write && surface.mcp` |
| `surface.cli` / `surface.mcp` | many | `surface.cli` / `surface.mcp` (CEL field access) |
| `cap:write` | tests | `cap.write` |
| `tool:foo` | tests | `tool.foo` |
| `default` | many | `default` (boolean atom) |

**Translation rules (proposed):**
1. `and` / `or` / `not` → `&&` / `\|\|` / `!`
2. `tool:foo` → `tool.foo` (atom becomes nested field access)
3. `cap:foo` → `cap.foo`
4. `surface.mcp` / `surface.cli` → unchanged (already CEL-compatible)
5. `default` → unchanged (boolean atom)
6. Atom evaluation context: `{tool: {<name>: bool}, cap: {<name>: bool}, surface: {mcp: bool, cli: bool}, default: bool}` populated per-tool from FastMCP `tags`.

**`validate_atoms` introspection callers** (in current code):
- `_select_eval._extract_atoms` walks the Pydantic AST.
- `runner._atom_polarity` and `_expr_mentions` introspect for capability-set warnings.

**Replacement**: cel-python's compiled program does not expose a clean AST walk for arbitrary atom extraction. Options:
- (a) A second cel-python parse-only pass with a custom visitor (`celpy.celparser.tree_dump` or similar).
- (b) Run the program against a sentinel context that records every accessed field; collect from the access log.
- (c) Pre-parse `--select` strings with a tiny regex to extract `tool.<name>` / `cap.<name>` references for warnings, separate from cel-python evaluation.

**Recommendation:** option (c) for warnings (cheap, predictable); option (b) at most. Don't attempt full AST walk over cel-python's tree.

**Open work for downstream coverage:** when `a2db` / `a2atlassian` / `a2web` checkouts are accessible, run `grep -rE "default|cap:|tool:|surface\." -- --select` and append findings to this section. Migration script (sed-based) covers the 6 rules above.

## Audit Findings — Round 2 (extra probes; landed 2026-05-09)

### Probe A — FastMCP composition surface vs `a2kit.App` ✅

**FastMCP `__init__` parameters** (verified): `name`, `instructions`, `version`, `auth`, `middleware`, `providers`, `transforms`, `lifespan`, `tools`, `on_duplicate`, `mask_error_details`, `dereference_schemas`, `strict_input_validation`, `list_page_size`, `tasks`, `session_state_store`, `sampling_handler`, `client_log_level`.

**a2kit.App's job today** (read `app.py`, 354 LOC): wraps a FastMCP instance + connection stores + router registry + dependency_overrides dict + Click CLI builder. Has lazy FastMCP import (no longer needed under D0).

**Overlap analysis:**
- `App.connect(ConnT)` → genuinely a2kit-specific (connection store registration). Stays.
- `App.use(Router)` → genuinely a2kit-specific (router abstraction). Stays.
- `App.cli` (Click group) → genuinely a2kit-specific (login/logout/serve + tool subcommands). Stays.
- `App.dependency_overrides` → DELETE (per T1.6, overrides happen at `connect()` time, not via runtime dict).
- `App.run/run_async/run_server` → wraps `MCPRunner.run()`. Could fold into `MCPRunner` directly; `App` keeps `.run()` as thin sugar.
- Lazy FastMCP import (`from mcp.server.fastmcp import FastMCP` inside `__init__`) → DELETE (FastMCP is now a hard dep; import at module top).

**Recommendation:** **Keep `App` but slim to ~150 LOC.** Delete `dependency_overrides`, lazy import, `_RESERVED_SUBCOMMANDS` (relies on tool-name collision check that's better expressed as a lint rule). Verify FastMCP's `on_duplicate` covers the same protection.

### Probe B — `Context` as tool parameter ✅ (high-impact finding)

**Verified:** FastMCP injects `ctx: Context` automatically when a tool function declares it. The parameter is **excluded from the user-facing input schema** (verified: `'ctx' in schema.properties == False`). `Context` exposes:

```
client_supports_extension, close_sse_stream, delete_state, debug, info, warning, error, log,
elicit, get_prompt, get_state, list_prompts, list_resources, list_roots,
read_resource, report_progress, sample, sample_step, send_notification, set_state
```

**Implication for a2kit:** the kit gets, for free, everything tool authors need for progress reporting, structured logging, MCP roots/prompts/resources access, and per-call state — without writing any plumbing. The "fat tool decorator" can stop owning context plumbing entirely.

**Combined with Probe A's finding** (FastMCP DI via `Depends`/`Dependency`):
- Connection injection: `*, conn: Annotated[TodoConn, Depends(get_conn)]` (FastMCP/uncalled_for handles it).
- MCP context: `*, ctx: Context` (FastMCP injects automatically).
- a2kit's `@tool` decorator's job shrinks to: `server.tool(annotations=..., tags=...)` plus a thin verb-classification layer (`@read`/`@write`/`@list`) plus the list-view post-processing middleware.

**Estimated `tool.py` after this**: ~80-120 LOC (down from earlier estimate of 200-300). Just the verb decorators + a thin metadata helper.

**Recommendation:** **Adopt FastMCP's `Context` parameter directly.** Tool authors who need progress / logging / roots use `ctx: Context` — same pattern they already know from FastMCP examples. a2kit ships zero context plumbing.

### Probe C — `add_tool_transformation` ⚠️ (DEPRECATED in FastMCP 3.x)

**Verified:** `FastMCP.add_tool_transformation()` emits a deprecation warning. Replacement: `add_transform(ToolTransform({...}))`. But neither is the right primitive for a2kit's pattern — both are *post-registration tool wrapping*, not *decoration-time tool registration*.

**Recommendation:** a2kit's `@tool` decorator does NOT use tool transformations. It calls `server.tool(annotations=..., tags=...)` directly (which is the documented FastMCP path).

### Probe D — cel-python compiles our pattern ✅

**Verified:** `tool.list_x && !write && surface.mcp` and `default && !write` compile and evaluate correctly. Missing-atom case (`{"default": True}` with `default && !write`) raises `celpy.CELEvalError("undeclared reference to 'write'")`.

**Recommendation:** `packages/select/` builds the activation context with **every known atom pre-populated as a real boolean** (so no missing-atom errors at evaluation time for legitimate expressions). For user typos (referencing an atom that doesn't exist), catch `CELEvalError` at evaluation and raise a typed `UnknownAtomError` with the offending name. Strict-mode is the default — typo detection beats silent `False`.

### Probe E — FastMCP streaming + `Context.report_progress` ✅

**Verified:** `Context.report_progress(...)` is the MCP-native progress mechanism. There is no FastMCP-level streaming-result primitive — tools return regular values; large results are returned as lists.

**a2kit's `streaming=True`** (in `@tool`): lets a tool return an `AsyncIterator[T]`; the list-view middleware drains the iterator and applies filter/fields. Currently gated by an explicit decorator flag.

**Finding:** the gate is unnecessary — the list-view middleware can detect `AsyncIterator` at runtime and drain unconditionally. The flag was a legacy v0.7 thing.

**Recommendation:** **Delete the `streaming=True` decorator flag.** The list-view middleware drains async iterators when it sees one. Simpler API; one less concept for tool authors. Tools that need granular progress use `ctx.report_progress()` directly via the `Context` parameter (Probe B).

### Probe G — MCP wire-level tag filtering ✅

**Verified:** `mcp.types.Tool` has `name`, `title`, `description`, `inputSchema`, `outputSchema`, `icons`, `annotations`, `meta`, `execution` — **but NOT `tags`**. Tags are a FastMCP-only server-side concept; the wire spec doesn't transmit them.

**Implication:** `--select` filtering must run **server-side at registration/listing time**, not as a wire-level filter. The unselected tools simply aren't registered (or are filtered out of `list_tools()` response). This matches a2kit's existing model.

**Recommendation:** `packages/select/` runs at `MCPRunner` boot — evaluates `--select` against each candidate tool's `(tags, annotations.readOnlyHint, annotations.destructiveHint, meta["a2kit"])` and registers only the survivors. No client-side filtering. No wire change.

**Bonus finding:** `mcp.types.Tool.meta` IS wire-level and CAN be used to surface non-filterable metadata (e.g., capability strings for debugging clients). Decision: don't surface tags via `meta` for now — keep them server-side as the spec intends.

### Net impact of Round-2 probes on the architecture

The earlier "thin core" estimate gets thinner:

| Concern | Earlier estimate | Round-2 verdict |
|---|---|---|
| `tool.py` LOC | 200-300 | **80-120** (Probe B: Context drops context plumbing) |
| `streaming=True` flag | kept | **deleted** (Probe E) |
| `dependency_overrides` on App | kept | **deleted** (Probe B + T1.6) |
| App lazy FastMCP import | kept | **deleted** (D0 hard dep) |
| `app.py` LOC | ~200 | **~150** |
| `--select` evaluator | tags-based | **tags + annotations + meta-based** (Probe G unchanged in semantics) |

Updated **core file count target: 9-10 files** (down from 12).
Updated **core LOC target: ~1.2K** (down from 2K).

## Audit Findings — Round 3 (open-question rolls; landed 2026-05-09)

### T1.1 — Downstream coverage ✅ RESOLVED (moot)

**Verified by reading `~/Workspaces/a2db/pyproject.toml` and `~/Workspaces/a2atlassian/pyproject.toml`:**

```
a2db (v0.2.3):       depends on `mcp[cli]>=1.9,<2`. NO `a2kit` dependency.
a2atlassian (v0.5.1): depends on `mcp[cli]>=1.9,<2` + `toon-format`. NO `a2kit` dependency.
a2web:                checkout not present locally.
```

**Implication:** there is no downstream migration cost for breaking a2kit. The "downstream MCP" framing in the README and prior planning was *aspirational*, not factual. a2kit's only consumers today are its own tests + `examples/`. T1.1 was inventorying expressions that don't exist.

**Action:** the CEL migration recipe in CHANGELOG remains useful as forward-looking guidance for future adopters, but **no coordinated downstream migration is needed**. Drop tasks 15.1, 15.2, 15.3 (downstream MCP bumps) — there's nothing to bump.

This makes the v1.0 break even cheaper than estimated. Zero coordination required.

### Probe — `on_duplicate` vs `_RESERVED_SUBCOMMANDS` ✅

**Verified:** FastMCP's `on_duplicate: Literal["warn", "error", "replace", "ignore"]` covers **tool-name vs tool-name** collisions only. It does NOT cover tool-name vs CLI-subcommand collisions (a2kit's concern).

**Conclusion:** `_RESERVED_SUBCOMMANDS` ({"serve", "login", "logout", "connections"}) check in `app.py` is a different concern. **Two options:**

1. Keep the check inside `App._build_cli()` (~10 LOC). Same as today.
2. Promote to a lint rule (would belong in `packages/lint/`). Catches it at decoration time, before runtime CLI build.

**Recommendation:** keep the runtime check (option 1). Adding a lint rule for one collision check is over-engineering. Plain `ValueError` at CLI build time is fine.

### Probe — `App.run` / `run_server` / `run_async` consolidation ✅

**Call sites (verified):**
- `app.run()` → builds CLI group, dispatches Click. Author-facing entry point.
- `app.run_server()` → bypasses Click; called from `app.cli.serve` and tests. The actual "start MCP" path.
- `app.run_async()` → async-host embedded path; only used by tests today.
- `argv=` kwarg on `run_server` is a v0.13 compat shim (line 322 in app.py).

**Recommendation:**

- Keep three methods, slim each:
  - `App.run()` — Click dispatch (author entry).
  - `App.run_server(*, options: RunnerOptions = RunnerOptions())` — direct sync start; **delete the `argv=` and `transport=` kwargs** (RunnerOptions covers them all).
  - `App.run_async(*, options: RunnerOptions = RunnerOptions())` — embedded async start; same kwarg cleanup.
- Drop the `argv: list[str] | None = None` parameter from both `run_server` and `run_async` — it was the v0.13 compat layer for argv round-tripping; RunnerOptions has been the canonical path since.

Net: ~50 LOC removed from `app.py` (~354 → ~150 with all the cleanups so far).

### Probe — `Tool.meta` mutability ✅ (high-impact)

**Verified:** FastMCP `Tool.meta` is mutable post-registration:

```python
@server.tool(meta={"a2kit": {"verb": "read"}})
def hello() -> str: ...
# tools[0].meta == {"a2kit": {"verb": "read"}}
# tools[0].meta = {"a2kit": {"verb": "write"}}  # ← works
# tools[0].get_meta() merges fastmcp internals: {"a2kit": ..., "fastmcp": {"tags": []}}
```

`Tool.get_meta()` returns a merged view including FastMCP-internal metadata (`fastmcp.tags`). Plain `Tool.meta` returns just the user-stamped portion.

**Conclusion:** **DELETE `metadata.py` entirely.** a2kit's WeakKeyDictionary tool registry is redundant. Stamp via `meta={"a2kit": {...}}` at decoration; read via `tool.meta["a2kit"]` in middlewares + select evaluator.

**Net effect:** core file count drops from 9-10 → **8-9**. `tool_metadata(fn)` accessor (currently in `metadata.py`) becomes a 5-line helper folded into `tool.py`:

```python
def tool_metadata(fn) -> dict | None:
    # Look up the registered Tool's a2kit meta
    ...
```

…or arguably users go straight at `server.get_tool(name).meta["a2kit"]` since that's the concrete API.

### Probe — `Provider` and `Transform` (FastMCP) vs `Router`/`RouterRegistry` (a2kit) ✅

**`Provider`**: dynamic component sourcing — a `Provider` subclass returns tools/resources/prompts on demand at list time. Used for proxying remote MCP servers (`ProxyProvider`), filesystem discovery, etc. Different concept from a2kit's `Router` (which is a static code-organization unit holding decorated functions).

**`Transform`** (`add_transform`): post-registration component modification — wraps a registered tool/resource. Different from a2kit's `@tool` decorator (which registers the tool in the first place).

**Conclusion:** No overlap. **`Router` / `RouterRegistry` stay as a2kit-owned primitives.** They serve a code-organization purpose FastMCP doesn't address.

(Bonus thought, NOT a recommendation: a future a2kit could expose a `Router` as a `Provider` for hot-reload scenarios. Out of scope.)

### Probe — `exceptions.py` audit ✅

**Read:** 199 LOC, 14 exception classes, all single-purpose, well-named.

**Two need pruning:**
- `ProjectionUnavailable` (lines 159-170) — DELETE. cel-python becomes a core dep under D2; "optional extra not installed" is no longer reachable.
- `MigrationRequired` (lines 59-89) — DELETE. v0.4 → v0.5 `KEY_FIELDS` migration is years dead. Fail with `TypeError("KEY_FIELDS is not supported; use key=NamedTuple")` if anyone hits it; the rich migration guide can move to docs.

**Two need a small move:**
- `ConnectionNotFound`, `InvalidConnectionKey`, `KeyFieldMissing`, `KeyArityMismatch`, `WriteNotAllowed`, `EnvVarNotFound`, `OpResolutionError`, `TokenResolutionError` — connection-related. Move to `packages/connections/exceptions.py` (or fold into `__init__.py`).
- `SchemaSnapshotMismatch` — testing-related. Move to `packages/testing/exceptions.py`.

**Stay in core `exceptions.py`:**
- `A2KitError` (base)
- `InvalidToolReturnTypeError` (decoration-time)
- `ToolCallContamination` (runtime middleware)
- `InvalidFilterExpression` (could move to `packages/select/`)

Net core `exceptions.py`: ~50 LOC, ~4 classes.

### Probe — `toon-format` PyPI package ⚠️ (encoder is a stub)

**Verified:** `toon-format==0.1.0` exists on PyPI. The `decode()` function works; the `encode()` function raises `NotImplementedError("TOON encoder is not yet implemented")`.

**Conclusion:** **a2kit keeps its in-house TOON encoder.** Re-evaluate when `toon-format` publishes a working encoder — at that point `packages/formatter/toon.py` could shrink by ~150 LOC.

(`a2atlassian` depends on `toon-format` as a forward-looking placeholder; same situation.)

## Audit Findings — Round 4 (library revalidations at latest versions; landed 2026-05-09)

User directive: install latest versions of every candidate library and revalidate prior judgements. Three of my earlier verdicts flipped.

### toon-format ✅ FLIPPED (was: stub; now: working encoder)

**Probed:** PyPI `toon-format==0.1.0` had `NotImplementedError` in `encode()`. **GitHub HEAD is `0.9.0-beta.1`** with a working encoder. Verified output:

```
[2]:
  - id: 1
    name: a
    tags[2]: x,y
  - id: 2
    name: b
    tags[1]: z
```

**Critical finding:** a2kit's current "TOON" format is **NOT real TOON**. It's TSV-with-JSON-cells, named after TOON but structurally different. Real TOON uses YAML-like indented blocks with `[N]:` length markers and `- ` list items. The MCP ecosystem (per `a2atlassian` adopting `toon-format`) is converging on the actual standard.

**Decision: ADOPT `toon-format` library.** Wire format changes for any consumer (zero downstream cost today per Round-3 T1.1). Drops the entire bespoke encoder + flat-fields decision tree from `packages/formatter/toon.py` — estimated ~200 LOC removal.

**Implementation note:** `format_response` returned `format=Literal["tsv", "toon", "json"]`. Under real TOON, the "tsv" branch goes away — TOON natively handles uniform-row lists (`[N]:\n  - field: value`). Drop "tsv" from the literal; just `"toon" | "json"`.

**Action:** Add `toon-format>=0.9` (or pin `git+https://github.com/toon-format/toon-python@main` until 0.9.0 ships to PyPI) to `packages/formatter/`'s required deps.

### pydantic-settings 2.14.1 ⚠️ PARTIALLY FLIPPED (was: rejected; now: re-open T1.2)

**Probed:** earlier audit (`todo.md:945-973`) and Round-1 T1.2 rejected pydantic-settings as a swap for `tokens.py` / `connections.py`. The latest version (2.14.1, published 2025) ships **far more than the prior probe knew**:

- `NestedSecretsSettingsSource` — handles secrets within nested models
- `AWSSecretsManagerSettingsSource`
- `AzureKeyVaultSettingsSource`
- `GoogleSecretManagerSettingsSource`
- `DotEnvSettingsSource`, `EnvSettingsSource`, `JsonConfigSettingsSource`, `TomlConfigSettingsSource`, `YamlConfigSettingsSource`, `PyprojectTomlConfigSettingsSource`, `SecretsSettingsSource`
- `CliSettingsSource` (full Click-style CLI integration)

**Re-evaluation:**

Contract A (status quo): keep `tokens.py` with pluggable `ResolverRegistry`. Pros: lazy, supports `${VAR}-inside-string` substitution. Cons: each new resolver (vault://, aws-sm://) is custom.

**Contract B (revalidated):** adopt pydantic-settings + revise contract.
- Built-in AWS / Azure / GCP secret-manager resolution — free. The prior probe didn't know about these.
- `${VAR}-inside-string` substitution still needs a custom `PydanticBaseSettingsSource` subclass (~30 LOC).
- Eager resolution at config load time (fail-fast).
- Total: a2kit ships 30-50 LOC of custom Source code, gets 4 cloud-secret backends + dotenv/json/toml/yaml for free.

**Updated recommendation:** **T1.2 re-opens.** Implementation T1.2 should produce a working spike of both:
- (A) keep `tokens.py` pluggable registry as-is.
- (B) custom `PydanticBaseSettingsSource` for `${VAR}` + adopt the cloud-secret built-ins.

Pick whichever is cleaner once both spikes exist. **Lean shifts toward B** — the cloud-secret coverage is real value a2kit gets for free.

### pyonepassword 5.3.0 ✅ CONFIRMED (rejection holds)

**Probed:** API surface = `OP.item_get`, `OP.item_get_password`, `OP.item_get_filename`, `OP.item_get_totp`, etc. Typed Python API instead of `subprocess.run(["op", "read", ...])`.

**Cost analysis:** still saves ~15 LOC vs current `tokens.resolve_op`. Pulls in 2 transitive deps (pyonepassword + python-singleton-metaclasses). Exception surface differs from `OpResolutionError`.

**Decision unchanged:** **don't adopt.** ~15 LOC saved is not worth 2 transitive deps + an exception-translation layer. `tokens.resolve_op` (subprocess wrapper) stays.

### cel-python 0.5.0 ✅ ATOM EXTRACTION VIABLE

**Probed:** `env.compile(expr)` returns a Lark `Tree`. The grammar uses `member_dot` nodes for `tool.foo` access:

```
member_dot
  member
    primary
      ident  tool
  foo
```

**Atom extraction is straightforward** via `tree.find_data('ident')` (bare atoms) + walking `member_dot` for dotted accesses. Strict-mode `validate_atoms(tree, known_atoms_dict)` is ~20 LOC.

**Action:** `packages/select/` ships:
- `compile(expr) -> CelProgram` — wraps `env.compile`.
- `evaluate(program, atoms_dict) -> bool` — wraps program execution; catches `CELEvalError` for unknown atoms; raises typed `UnknownAtomError`.
- `validate_atoms(expr, known_atoms) -> None` — Lark Tree walk; raises if expression references atoms not in `known_atoms`.

Estimated ~80-100 LOC for the whole `packages/select/` package.

### syrupy 5.1.0 ✅ FLIPPED (was: rejected; now: adopt with SingleFileSnapshotExtension)

**Probed:** earlier T1.5 rejected syrupy because the standard pattern is one snapshot file per test, not per tool. **Latest syrupy ships `SingleFileSnapshotExtension`** (`syrupy.extensions.single_file`) which writes one file per snapshot. With a custom subclass overriding `get_snapshot_name()` and `dirname()`, a2kit can:

- Write one file per registered tool (`<tool_name>.json`).
- Use the binary write mode for byte-accurate `os.path.getsize()` token-budget assertions.
- Get update-snapshot CLI (`pytest --snapshot-update`) for free.
- Get unified-diff failure messages for free.

**Decision: ADOPT syrupy.** `packages/testing/` ships a custom `SingleFileSnapshotExtension` subclass (~30-50 LOC) that handles the per-tool-file convention. Drops `snapshot_schemas` + `assert_schemas_match` (~80 LOC) and replaces them with the syrupy fixture pattern. Net: ~30-50 LOC instead of ~80, plus the free snapshot-management ergonomics.

**Implementation:**
```python
# packages/testing/snapshots.py
from syrupy.extensions.single_file import SingleFileSnapshotExtension

class A2KitToolSchemaExtension(SingleFileSnapshotExtension):
    file_extension = "json"
    @classmethod
    def get_snapshot_name(cls, *, test_location, index=0):
        # use the tool name (passed via fixture parameter) instead of test name
        ...
```

Tests then write:
```python
def test_tool_schema(snapshot, schema_for_tool):
    assert schema_for_tool("get_issue") == snapshot(extension_class=A2KitToolSchemaExtension)
```

### Net effect of Round-4 revalidations on the architecture

| Change | LOC delta | Wire impact |
|---|---|---|
| Adopt `toon-format` | -200 (a2kit's bespoke encoder) | **breaking** wire format change (TSV-with-JSON → real TOON) |
| T1.2 re-opens (Contract B more viable) | -50 to -100 if Contract B wins | none (config-time loading) |
| Adopt syrupy with SingleFileSnapshotExtension | -50 (snapshot wrappers) | none (test infrastructure) |
| `pyonepassword` rejected (confirmed) | 0 | none |
| `cel-python` AST extraction confirmed viable | 0 | none |

Combined with prior rounds, the revised core estimate:

| | Earlier (Round 2) | Now (Round 4) |
|---|---|---|
| Core files | 8-10 | **8-9** |
| Core LOC | ~1.2K | **~1.1K** |
| `packages/formatter/` LOC | ~320 | **~120** (after toon-format adoption) |
| `packages/testing/` LOC | ~90 | **~50** (after syrupy adoption) |
| Total source LOC (core + packages) | ~3.5K | **~2.7K** (down from 7.9K, ~66% reduction) |

## Audit Findings — Round 5 (deeper validations; landed 2026-05-09)

### F1 — `App.run/run_server/run_async` are redundant; FastMCP ships its own CLI ✅ (high impact)

**Probed:** `fastmcp` package ships `fastmcp.cli` with console_script `fastmcp` exposing:
- `fastmcp run <server.py>` — start an MCP server
- `fastmcp dev` — dev mode with hot-reload
- `fastmcp inspect`, `fastmcp list`, `fastmcp call` — tool introspection
- `fastmcp install` — install in MCP clients
- `fastmcp project`, `fastmcp tasks`, `fastmcp auth` — project/task/auth management

**Verdict:** a2kit's Click scaffold (`App.run`, `App.run_server`, `App.run_async`, the `serve` subcommand, the per-tool subcommand generation) is **redundant**. FastMCP's CLI covers all of it.

**What's a2kit-specific:** connection management (`login`/`logout`/`connections list/show/delete`) — a2kit owns `~/.config/a2kit/connections/`, FastMCP doesn't.

**Recommendation: DELETE `App.run/run_server/run_async`.** a2kit ships:
- `App` keeps `connect()` and `use(Router)` as composition primitives.
- `cli.py` shrinks to a `a2kit connections` Click group with `login`, `logout`, `list`, `show`, `delete` subcommands. ~80-100 LOC total.

**User composition pattern:**
```bash
$ a2kit connections login prod url=https://... token=${ATL}
$ fastmcp run my_server.py        # FastMCP owns serve
```

The MCP author's `server.py` builds an `App`, attaches routers, and exposes `app.server` (the underlying FastMCP instance) as the module-level `server` that `fastmcp run` discovers. No `app.run()` line.

**LOC impact:** `app.py` from current 354 → estimated ~80 LOC (just `connect`/`use`/exposing `.server`). `cli.py` becomes a connection-management group, not a full app entry. **Drops ~150 LOC** vs the prior estimate.

Updated core file count: `cli.py` becomes essentially the connection-management CLI; not a full app dispatcher.

### F2 — Cold-start crisis: lint CLI cannot afford FastMCP import ⚠️ (structural)

**Probed cold-start cost (verified):**

| Import | Time |
|---|---|
| `click` only | 40ms |
| `uncalled_for` only | 71ms |
| `mcp` only | 616ms |
| `mcp.types` | 570ms |
| `fastmcp.dependencies` (just Depends) | 1.1s |
| `import fastmcp` | **6.8s cold / 3.6s warm** |

**Implication:** if `a2kit/__init__.py` imports anything from `fastmcp`, then `a2kit lint` (the lint CLI) pays 3-7s on every invocation for nothing — the linter doesn't need FastMCP at runtime, it's a static analyzer.

**Discipline rule:** `packages/lint/*` modules import only stdlib + Click + Python AST + a2kit's lint internals. **NO `from a2kit import App` at module top.** If a lint rule needs to introspect a2kit's runtime concepts, it does so via AST patterns (string-matching the symbol name), not by importing.

This is enforceable as a lint rule (irony noted): `packages/lint/*` cannot `import a2kit.app|tool|routers|runner|connections|select|formatter`.

**`a2kit/__init__.py` discipline:** keep top-level imports lazy if they would chain into fastmcp. Specifically: `App` (which constructs FastMCP) imports fastmcp inside its body, not at module top. Same for any module that re-exports App.

This refines D14 (`__init__.py` minimization): the kit's own __init__.py imports from a2kit.app, a2kit.routers, etc. Those modules import fastmcp at their tops (they need it). So `import a2kit` triggers fastmcp's 3.6s warm import. **For lint-only invocations, the lint CLI must use a different entry path** — e.g. `python -m a2kit.packages.lint.cli` which only imports `a2kit.packages.lint.*`.

**Recommendation:** the `a2kit` console script (`a2kit = "a2kit.packages.lint.cli:main"`) is structurally fine *as long as* the cli module doesn't import from a2kit's runtime. Verify this with a startup-time test in CI: `time python -c 'import a2kit.packages.lint.cli'` must be <300ms.

### F3 — `Depends` import path: `uncalled_for` direct, not `fastmcp` top-level ✅

**Probed:** top-level `fastmcp` does NOT re-export `Depends`. Path is `from fastmcp.dependencies import Depends`. But the canonical owner is `uncalled_for` (FastMCP imports `Depends` from there).

**Per D17 (no re-exports):** users import from the owning library. So:

- `from uncalled_for import Depends` ← cleanest, fastest cold-start (71ms)
- `from fastmcp.dependencies import Depends` ← also valid, slower cold-start (1.1s for the dependencies module)

**Recommendation:** documentation prefers `from uncalled_for import Depends`. Migration guide includes both paths but recommends the lighter import.

Side benefit: `uncalled_for` is a small focused library; users learning the DI pattern see a clean surface (Dependency, Depends, Shared, SharedContext) rather than getting it bundled with all of fastmcp.

### F4 — Release stability ✅

**Probed PyPI release histories:**
- **FastMCP**: 3.0.0 in Feb 2026; 3.2.4 in April 2026. Stable major release line. Multiple 3.x releases per month; active maintenance. 2.x still maintained in parallel (2.14.7 in April 2026) — long migration window. **Pin `>=3.2,<4` durable for 6-12 months.**
- **uncalled_for**: 0.3.2 published 2026-05-06 (three days ago at audit time). Pre-1.0, bleeding edge. **Inherited transitively via FastMCP — do NOT pin directly.** Let FastMCP's pin flow through. If it breaks, it breaks via FastMCP's pin update.
- **cel-python**: 0.5.0 in Jan 2026. Slow release cadence (~yearly). Stable. **Pin `>=0.5,<0.6` durable.**

### F5 — `examples/tracker/` migration spike ✅

**Mechanical changes** (read `examples/tracker/server.py` and `routers.py`):

| Current | New |
|---|---|
| `from a2kit.di import Depends` | `from uncalled_for import Depends` |
| `from a2kit.contrib.connections import get_conn_factory` | `from a2kit.packages.connections import get_conn_factory` |
| `app.run()` (last line of `main()`) | **delete** — author exposes `server = app.server` at module level for `fastmcp run` |
| `set_get_conn(...)` | unchanged (tracker-specific helper) |
| `@ProjectsRouter.list/read/write` | unchanged |
| Connection injection via `*, conn: Annotated[TrackerConn, Depends(get_conn)]` | unchanged |
| `app.connect(TrackerConn)` | unchanged |
| `app.use(ProjectsRouter)` | unchanged |

**Author runtime command:**
```bash
$ fastmcp run examples/tracker/server.py
```

That's it. **Migration is two import-path swaps + delete one line.** Confirms the design holds end-to-end.

### F6 — DI override spike (incomplete; needs deeper test)

**Attempted:** worked through a spike (`@server.tool() async def query(*, db: Annotated[str, Depends(real_db)])`) but the test crashed before exercising the override mechanism — `await server.call_tool("query", {})` hit an unrelated error path.

**Status:** override pattern not yet validated end-to-end. T1.6's recommendation (use `SharedContext.resolved` pre-population OR `Shared` factory replacement at registration time) **stands as a hypothesis, not a verified pattern.**

**Action:** when implementation begins, the FIRST task before T7 (tool decorator split) is a working test fixture that overrides a `Depends(get_conn)` in a unit test. If the canonical `uncalled_for` pattern doesn't work for our shape, surface the gap before code lands.

This bumps T1.6 from "audit complete" back to "needs implementation-time validation."

## Audit Findings — Round 6 (P3 + uncalled_for canonical + progressive disclosure; landed 2026-05-09)

### Probe I — Router pre-decoration → FastMCP binding ✅ verified end-to-end

```python
# Pre-decorate at module load (no fastmcp):
async def list_tasks(project_id: str | None = None) -> list[dict]: ...
list_tasks._a2kit = {"verb": "list", "tags": {"read"}, ...}

# Bind at runtime (packages/mcp/build_mcp_server):
from fastmcp.tools.function_tool import FunctionTool
tool = FunctionTool.from_function(
    list_tasks,
    name="list_tasks",
    tags=list_tasks._a2kit["tags"],
    annotations=ToolAnnotations(readOnlyHint=True),
    meta={"a2kit": {...}},
)
server.add_tool(tool)
# Verified: tags survive, annotations survive, meta.a2kit survives, call works.
```

### Probe D — Tracker migration walkthrough (concrete) ✅

`examples/tracker/server.py` decomposes into three thin entries:

**`app.py`** (no fastmcp, no click):
```python
import a2kit
from a2kit.packages.connections import get_conn_factory
from .connection import TrackerConn
from .deps import set_get_conn
from .routers import ProjectsRouter, TasksRouter

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
set_get_conn(get_conn_factory(app, TrackerConn))
app.use(ProjectsRouter)
app.use(TasksRouter)
```

**`mcp_server.py`** (loads fastmcp, used by `fastmcp run`):
```python
from .app import app
from a2kit.packages.mcp import build_mcp_server
server = build_mcp_server(app)
```

**`cli.py`** (loads click + uncalled_for, no fastmcp):
```python
from .app import app
from a2kit.packages.cli import build_cli
if __name__ == "__main__":
    build_cli(app)()
```

**Routers** (`routers.py`) — DI migration:
```python
# Before (a2kit di.py — to be deleted):
from a2kit.di import Depends
async def list_projects(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[Project]: ...

# After (uncalled_for canonical):
from uncalled_for import Depends
async def list_projects(*, conn: TrackerConn = Depends(get_conn)) -> list[Project]: ...
```

**That's it.** Two-line module decomposition + one-line DI migration per fn. Mechanical.

## Audit Findings — Round 7 (final closeout; landed 2026-05-09)

### T1.6 DI override through FastMCP adapter ✅ VERIFIED

Spiked end-to-end with `FunctionTool.from_function` + `server.add_tool` + `server.call_tool`.

**Pattern that works:** build a fresh FastMCP server with a different fn variant (different `Depends(factory)`). uncalled_for resolves Depends at call time per registered fn; swapping the fn at registration swaps the resolution.

```python
async def get_db_real(): return {"kind": "REAL"}
async def get_db_fake(): return {"kind": "FAKE"}

# real
async def query(*, db: dict = Depends(get_db_real)) -> dict: return {"db": db}
server_real = FastMCP("real")
server_real.add_tool(FunctionTool.from_function(query, name="query"))

# test
async def query_test(*, db: dict = Depends(get_db_fake)) -> dict: return {"db": db}
server_test = FastMCP("test")
server_test.add_tool(FunctionTool.from_function(query_test, name="query"))
# server_test.call_tool("query", {}) → {"db": {"kind": "FAKE"}}
```

**Pattern that doesn't work:** `await server.call_tool("query", {"db": fake_value})` — FastMCP's input-schema validation rejects DI parameters as "unexpected keyword argument" (since DI deps are stripped from the schema). Confirmed: the value-injection-via-args path is closed at the adapter layer.

**Recommendation for `packages/testing/`:** ship a `make_test_app(routers, overrides: dict[Callable, Callable])` helper that rebuilds the App with overridden Depends factories at construction time. ~30 LOC. No runtime override map.

### `toon-format` PyPI release ✅ ALREADY THERE

`toon-format==0.9.0b1` published to PyPI on 2025-11-08 (six months ago). No need to pin from GitHub. Use `toon-format>=0.9.0b1` in `packages/formatter/`.

Verified encoder works directly from PyPI install:
```
$ pip install --pre 'toon-format>=0.9.0b1'
$ python -c "import toon_format; print(toon_format.encode([{'a':1,'b':2},{'a':3,'b':4}]))"
[2]{a,b}:
  1,2
  3,4
```

### Single-entry `a2kit.run(app)` LazyGroup pattern ✅ VERIFIED

Spiked the full pattern:
- Click `LazyGroup` at root; `serve` is a lazy subcommand pointing at `a2kit.packages.mcp.cli.serve_command`.
- ContextVar `_APP_CTX` carries the user's `App` to whichever subcommand fires.
- Eager subgroups: one per Router + `connections`. All fastmcp-free.
- Lazy subgroup: `serve` only imports its module when invoked.

Confirmed by spike: after running `tracker tasks list-tasks ...` and `tracker connections list`, `'fastmcp' in sys.modules == False`. Only `tracker serve` triggers fastmcp import.

`tracker --help` output shows all subgroups (eager + lazy) without loading the lazy ones — Click's `list_commands` introspects the `lazy_subcommands` dict for listing.

### `App` survives — ~50 LOC class ✅ DECIDED

`App` keeps `connect(ConnT)`, `use(Router)`, `get_store(ConnT)` as methods. No `.run()`. No FastMCP. Pure registry. Estimated ~50 LOC. Stays a class (not a dataclass) because `connect()` returns the store and `use()` is a verb that mutates state — methods read better than `_attach_router(app, router)`.

## Audit Findings — Round 8 (final implementation gotchas; landed 2026-05-09)

Eight final hypotheses tested. Five clean, three with subtle gotchas worth flagging.

### Verified clean

- **A — pydantic-settings + `${VAR}` substitution** via custom `PydanticBaseSettingsSource`: works. Eager resolution at construction; fails fast on missing env var.
- **D — NamedTuple `Key` + `ClassVar` survives `BaseSettings` inheritance**: verified. `__init_subclass__(key=...)` machinery from current `connections.py` ports cleanly.
- **E — `uncalled_for.without_dependencies(fn)` strips DI from signature**: verified. `*, project_id: str | None = None, conn: dict = Depends(get_conn)` becomes `*, project_id: str | None = None`. Calling the stripped fn auto-resolves Depends.
- **F — `pydantic.create_model` from stripped signature → MCP-compatible JSON schema**: verified. `project_id: str | None = None` produces `{"anyOf":[{"type":"string"},{"type":"null"}], "default": null}` cleanly.
- **H — PEP 562 lazy attrs**: nearly zero cost. `a2kit/__init__.py` with `__getattr__` and `_LAZY_ATTRS` dict is effectively free; runtime modules only load on first attribute access.

### Gotcha 1 — Save/load round-trip leaks resolved secrets to disk ⚠️

Under Contract B's eager resolution, calling `model_dump()` on a loaded config returns the **resolved** values (the real token), not the original placeholders. Naively `store.save(loaded_config)` would persist the secret value to disk on round-trip.

**Reproduced:**
```python
cfg = JiraConfig(token="${MY_TOKEN}")    # → cfg.token == "real-secret-value-123"
cfg.model_dump()                          # → {"token": "real-secret-value-123"}  ❌ leaked
```

**Fix (verified):** capture `init_kwargs` into a `PrivateAttr` shadow; expose a `serialize_to_disk()` method that returns the raw form.

```python
class ConnectionConfig(BaseSettings):
    _raw: dict = PrivateAttr(default_factory=dict)
    def __init__(self, **data):
        super().__init__(**data)
        self._raw = dict(data)
    def serialize_to_disk(self) -> dict:
        return self._raw
```

`store.save(cfg)` MUST call `cfg.serialize_to_disk()`, not `cfg.model_dump()`. Lint rule could enforce this. Capturing as **implementation requirement: ConnectionStore round-trip preserves raw placeholders, never persists resolved values**.

### Gotcha 2 — `toon-format` install needs `--pre` or exact pin ⚠️

`uv pip install toon-format` defaults to the stale 0.1.0 stub (encoder = `NotImplementedError`). Only `--pre` or exact-pin gets 0.9.0b1 with the working encoder.

**Verified:**
```
$ uv pip install toon-format             # → 0.1.0 (stub)
$ uv pip install --pre 'toon-format>=0.9.0b1'  # → 0.9.0b1 (working)
```

**Fix:** pin exactly in `packages/formatter/`'s declared deps:
```
toon-format = "==0.9.0b1"
```

Or until 1.0 ships, document the `--pre` requirement in install instructions. Track upstream and bump when 1.0 lands.

### Gotcha 3 — `pydantic.validate_call` doesn't catch Depends misuse ⚠️

`pydantic.validate_call(fn)` on a function with `*, conn: dict = Depends(get_conn)` does **not** raise. It silently passes the `_Depends` sentinel object through as the `conn` value:

```python
validated = pydantic.validate_call(my_tool)
await validated(x=42)
# → {'conn': <_Depends object at 0x...>, 'x': 42}   ❌ leaked sentinel
```

This is a footgun for anyone bypassing `without_dependencies(fn)` and reaching for pydantic directly. Not a blocker (a2kit always strips via `without_dependencies` first), but warrants a lint rule.

**Fix:** add lint rule **A2K-DI-PYDANTIC-VALIDATE** — flag `pydantic.validate_call(fn)` on any fn whose signature contains a `_Depends` default. Suggested message: *"Always run `without_dependencies(fn)` before pydantic validation; otherwise the Depends sentinel leaks as the parameter value."*

### Net effect on implementation tasks

Three new line items for `tasks.md`:

1. `ConnectionConfig` round-trip uses `_raw: PrivateAttr` shadow + `serialize_to_disk()` method. `store.save(cfg)` calls the latter. Tests cover the round-trip preservation.
2. `packages/formatter/` pins `toon-format==0.9.0b1` exact (or git ref). Document the `--pre` install requirement until 1.0 ships.
3. Lint rule A2K-DI-PYDANTIC-VALIDATE flags `validate_call(fn)` on Depends-defaulted fns.

## Audit Findings — Round 9 (final pre-implementation: behavioral + risk-radius; landed 2026-05-09)

### Behavioral hypotheses

#### B5 — `from __future__ import annotations` works under uncalled_for ✅ (busts a stale concern)

`tracker/routers.py:21-24` carries a comment warning against future annotations because a2kit's own `di.py` needs `typing.get_type_hints(include_extras=True)` to find `Annotated[T, Depends(...)]` metadata.

**Verified:** under uncalled_for canonical (parameter-default form `*, conn: dict = Depends(get_conn)`), future annotations do NOT break introspection. `inspect.signature(fn).parameters['db'].default` returns the `_Depends` object regardless of how the type annotation is stringified. uncalled_for reads defaults, not type hints.

**Implication:** a2kit's tool fns CAN use `from __future__ import annotations` post-migration. The legacy comment is stale. Drop it.

#### B6 — Sync tool bodies work transparently ✅

`def fn(...)` (sync) and `async def fn(...)` both work through:
- FastMCP `FunctionTool.from_function` → `server.add_tool` (FastMCP wraps sync→async internally)
- `uncalled_for.without_dependencies(sync_fn)` → returns an async wrapper

a2kit doesn't need branching for sync vs async. **One code path covers both.**

#### B9 — Pydantic schema generation handles all typical generics ✅

Verified against `list[Project]`, `Project`, `dict[str, str]`, `Optional[Project]`, `list[dict[str, Any]]`, `Project | None`. All produce correct JSON schemas with proper `$defs` / `$ref` for nested Pydantic models.

For input-side `pydantic.create_model(**fields)` with `Project | None` defaults: produces `{"anyOf": [{"$ref": "#/$defs/Project"}, {"type": "null"}], "default": null}` — clean MCP-compatible output.

**Implication:** schema discovery surface is more capable than initially assumed. Users can return rich nested types and schemas just work.

#### B10 — Substitution gotcha: `${VAR}` doesn't recurse into list/dict fields ⚠️

Verified: pydantic-settings custom Source substitutes top-level string fields and lets pydantic coerce types post-substitution. `port="${NUM}"` → `port=42` (int). `enabled="${FLAG}"` → `enabled=True` (bool).

**But:** `tags=["${NUM}", "literal"]` → `tags=["${NUM}", "literal"]` — placeholder NOT substituted because the source only walks top-level dict values.

**Decision:** acceptable limitation. Connection configs are flat in practice (url, token, region as strings). If users need list-internal substitution, document the workaround: declare individual fields (`tag1`, `tag2`, ...) or post-process at field validator level. Add `A2K-CONN-LIST-PLACEHOLDER` lint rule that flags `${VAR}` inside list/dict literals on `ConnectionConfig` subclasses.

#### B1 — Error semantics through MCP adapter ✅ (with note)

Verified: a tool raising `TrackerError("x cannot be zero")` surfaces at the MCP adapter as `ToolError: Error calling tool 'fail_tool': x cannot be zero`. Type is wrapped; message is preserved.

**For the enricher pattern:** the enricher middleware (subclass of `fastmcp.server.middleware.Middleware`) hooks `on_call_tool`, runs `await call_next(...)` inside try/except, catches the **original** exception (BEFORE FastMCP's ToolError wrapping happens — middleware runs in the inner chain). Confirmed: enrichers see and can transform the user's exception type before it bubbles to the wire.

### I3 — PEP 562 + IDE autocomplete

PEP 562 `__getattr__` is supported by mypy and pyright at runtime, but static analyzers can't track lazy attrs *only* from the dunder. **Standard pattern:** declare imports under `if TYPE_CHECKING:` so type checkers see them without runtime cost:

```python
# a2kit/__init__.py
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.app import App
    from a2kit.routers import Router, RouterRegistry
    from a2kit.tool import tool, read, write, list_

_LAZY_ATTRS = {
    "App": ("a2kit.app", "App"),
    "Router": ("a2kit.routers", "Router"),
    # ...
}

def __getattr__(name: str):
    if name in _LAZY_ATTRS:
        from importlib import import_module
        mod, attr = _LAZY_ATTRS[name]
        return getattr(import_module(mod), attr)
    raise AttributeError(f"module 'a2kit' has no attribute {name!r}")
```

Type checkers see the eager imports; runtime sees only the dunder. IDE autocomplete works. Cold-start stays fast. **Best of both.**

### D1 — `uvx <pkg>` invocation pattern

uvx invokes `[project.scripts] tool = "pkg.module:fn"` after pulling deps. With:

```python
# pkg/server.py
import a2kit
app = a2kit.App("tool")
# ... configure ...
def main() -> None:
    a2kit.run(app)
```

```toml
[project.scripts]
tool = "pkg.server:main"
```

`uvx tool` works as documented. No special probe needed; standard uv behavior.

### Risk-radius matrix

| External surface | Used in | Wide blast radius? | Mitigation |
|---|---|---|---|
| `fastmcp` (`FastMCP`, `FunctionTool.from_function`, `Middleware`, `MiddlewareContext`) | `packages/mcp/` ONLY | NO — one package | Pin `fastmcp>=3.2,<4`; if 4.0 breaks, fix one adapter |
| `uncalled_for` (`Depends`, `without_dependencies`) | **every user tool fn** + `packages/cli/` + `packages/testing/` | **YES — every tool fn** | Pin `>=0.3,<0.4`; pre-1.0 risk; document migration if breaks. **Most exposed dep.** |
| `mcp.types.ToolAnnotations` | `tool.py` decorator | NO — one decorator | MCP spec is stable |
| `pydantic` (BaseModel, create_model, TypeAdapter, json_schema, ConfigDict, PrivateAttr) | everywhere | wide, but extremely stable | Pin `>=2,<3`; pydantic 2.x has strong stability guarantees |
| `pydantic-settings` (BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource) | `packages/connections/` | NO — one package | Pin `>=2.14,<3` |
| `cel-python` (`Environment`, Lark Tree) | `packages/select/` | NO — one package | Slow release cadence; minimal API surface used |
| `toon-format` (`encode`) | `packages/formatter/` | NO — one package | Pin `==0.9.0b1` exact; bump when 1.0 ships |
| `click` | `packages/cli/`, `packages/lint/` | medium — two packages | Click 8 is mature; LazyGroup pattern stable |
| `syrupy` | `packages/testing/` | NO | SingleFileSnapshotExtension is stable; minimal usage |
| `vcrpy` | `packages/testing/` | NO | Mature lib, narrow usage |

**Wide-radius dependencies (worth attention):** `uncalled_for` (every tool fn) and `pydantic` (everywhere).

`pydantic` is mature; not a real concern. **`uncalled_for` is the single biggest risk-radius item** — pre-1.0, single maintainer, two months old, and every user tool fn uses it.

**Mitigation options for uncalled_for:**

1. **Pin and watch.** Pin `uncalled-for>=0.3,<0.4`. Track upstream releases. Bump deliberately. Document migration path if breakage ships. **Recommended — cheapest.**
2. **Wrapper layer.** Ship `a2kit.di` as a paper-thin re-export (~30 LOC) that abstracts uncalled_for behind an a2kit-owned API. Insulates users from breakage. **Cost: violates D17 (no re-exports), more code, more cognitive overhead.** Reject.
3. **Vendor.** Bundle uncalled_for source into a2kit. **Cost: hard to keep current, license complications.** Reject.

**Decision:** Option 1. Pin tightly, document risk in CHANGELOG, write migration notes if upstream breaks.

### `A2KitMeta` — formal thin-waist contract ✅ NEW

Every adapter (`packages/mcp/`, `packages/cli/`, `packages/select/`, `packages/lint/`, `packages/testing/`) reads `fn._a2kit` to drive its work. If that's an untyped dict, every reader carries implicit knowledge of string keys. Refactoring becomes brittle.

**Decision: define `A2KitMeta` as a frozen dataclass** in `a2kit/_meta.py` (or fold into `a2kit/tool.py`):

```python
@dataclass(frozen=True, slots=True)
class A2KitMeta:
    tool_name: str
    verb: Literal["read", "write", "list", "tool"]
    tags: frozenset[str]
    annotations: ToolAnnotations  # mcp.types.ToolAnnotations
    router_slug: str | None
    list_view: ListViewSettings | None  # filter/fields/pagination shape
    enricher: EnricherFn | None
```

Stamping (in `tool.py` decorator):

```python
def read(name: str | None = None, **kw):
    def deco(fn):
        fn._a2kit = A2KitMeta(
            tool_name=name or fn.__name__,
            verb="read",
            tags=frozenset({"read"}),
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
            router_slug=kw.get("router_slug"),
            list_view=None,
            enricher=kw.get("enricher"),
        )
        return fn
    return deco
```

Reading (every adapter):

```python
meta: A2KitMeta = fn._a2kit
tool = FunctionTool.from_function(fn, name=meta.tool_name, tags=set(meta.tags), annotations=meta.annotations)
```

**Net effect:** mypy/pyright catch every typo or missing field. Refactoring `A2KitMeta` (e.g. adding a field) flags every reader at compile time. The contract is **typed, frozen, documented in one place**.

This is the single most important risk-radius reduction available — it converts an implicit contract (string keys in a dict) into an explicit one (typed dataclass).

### Net effect on tasks

Five new line items for `tasks.md`:

1. Define `A2KitMeta` frozen dataclass; every adapter consumes the typed instance.
2. `a2kit/__init__.py` uses `if TYPE_CHECKING:` for IDE autocomplete + PEP 562 lazy attrs for runtime.
3. Drop the stale "no future annotations" comment from `examples/tracker/routers.py`.
4. Add `A2K-CONN-LIST-PLACEHOLDER` lint rule for `${VAR}` inside list/dict literals on `ConnectionConfig`.
5. Pin `uncalled-for>=0.3,<0.4` with CHANGELOG note about pre-1.0 risk.

## Audit Findings — Round 10 (LLM-surface generalization; landed 2026-05-09)

User direction: every LLM-facing surface should be optimized AND optimizable. Errors, output formatting, and schemas should all flow through a2kit's optimization layer, regardless of whether the consumer is MCP or CLI.

### D-Enricher-Protocol-Neutral: enrichers wrap tools at decoration; both adapters honor them ✅ CORRECTED

Earlier rounds positioned the error enricher as a FastMCP middleware subclass (`packages/middlewares/enricher.py`). **Wrong scope.** Enrichers are protocol-neutral and must work identically for MCP and CLI invocations.

**Revised shape:** `packages/enrichers/` ships:

```python
# packages/enrichers/__init__.py
EnricherFn = Callable[[Exception, str], Exception]

def chain(*enrichers: EnricherFn) -> EnricherFn:
    """Compose enrichers; each wraps the next."""
    ...

def wrap(fn: Callable, enricher: EnricherFn | None) -> Callable:
    """Return fn wrapped with try/except → enricher transform.
    
    Works for sync and async fns transparently.
    """
    ...

def connection_enricher(store: ConnectionStore) -> EnricherFn:
    """Pre-built enricher that adds connection-load-failure context."""
    ...
```

Both adapters apply `wrap(fn, meta.enricher)` to each tool fn at registration time:
- `packages/mcp/build_mcp_server`: passes the wrapped fn to `FunctionTool.from_function`.
- `packages/cli/build_cli`: passes the wrapped fn into the Click subcommand handler.

**No FastMCP `Middleware` subclass needed for enrichers.** This eliminates the `packages/middlewares/enricher.py` module entirely; logic moves to `packages/enrichers/__init__.py` as a generic wrapper. ~50 LOC.

### D-CLI-Output-Formatter: CLI output flows through the formatter, same as MCP ✅ NEW

User direction: CLI tool results must use the same TSV / TOON / JSON heuristic as MCP results. The formatter is the single output-normalization layer.

**Revised CLI invocation flow** (`packages/cli/`):

```python
async def _invoke_tool_in_process(fn, kwargs, format: str = "auto"):
    from a2kit.packages.formatter import format_response
    wrapped = without_dependencies(fn)        # strip DI
    enriched = enrichers_wrap(wrapped, fn._a2kit.enricher)
    raw = await enriched(**kwargs)
    response = format_response(raw, format_hint=format)  # TSV / TOON / JSON
    click.echo(response.data)                  # to stdout
```

Tool subcommand accepts `--format=auto|tsv|toon|json` flag (default: `auto` — uses the heuristic). Output is byte-identical to what the MCP adapter would send over the wire. Predictable token cost regardless of consumer.

### D-Schema-As-TOON: schema output uses formatter; TOON default for token efficiency ✅ NEW

User direction: schema output should leverage TOON's token efficiency. The schema dict is structured nested data — TOON encodes it ~50% smaller than JSON.

**Revised `tracker schema` command:**

```bash
$ tracker schema list_tasks                 # default: TOON
$ tracker schema list_tasks --format=json   # opt-in: JSON
$ tracker schema --format=toon              # all tools, TOON
```

**Implementation:** `packages/cli/schemas.py` calls `format_response(schema_dict, format_hint=format)` instead of `json.dumps(...)`. Schema generation produces the dict; the formatter encodes it.

**Per-tool snapshots:** `packages/testing/` SingleFileSnapshotExtension also uses TOON. File contents are identical to `tracker <router> <tool> --schema --format=toon`. Drift detection + token-budget contract in one byte stream.

**Trade-off:** the JSON schema convention is universal; TOON is a2kit-specific. Tools/IDEs that consume schemas via JSON Schema (e.g., type-checkers, code generators) need JSON. Mitigation: `--format=json` always available; documented in CLI help; CI integration recipes default to JSON.

### Net effect

- **`packages/middlewares/enricher.py` deleted.** Enricher logic in `packages/enrichers/` (protocol-neutral).
- **`packages/cli/` invocation handler reuses `format_response`.** No duplicated formatting code.
- **`packages/cli/schemas.py` outputs TOON by default.** Schema = optimizable LLM surface.
- **`packages/testing/` snapshot files use TOON.** Same byte stream as `tracker schema --format=toon`.

The formatter becomes the **single optimization waist** for all LLM-facing output: tool results, schemas, snapshots. One place to tune; one place to evolve.

## Audit Findings — Round 11 (logging + progress streaming; landed 2026-05-09)

User direction: tools need realtime status / progress streaming. Both MCP and CLI consumers should get it; CLI logs should be LLM-friendly text, not JSON.

### D-ToolContext-Protocol: protocol-neutral logging + progress ✅ NEW

**Core ships a `ToolContext` Protocol** in `a2kit/runtime.py`:

```python
from typing import Protocol, Any

class ToolContext(Protocol):
    """Protocol-neutral logging + progress for tool bodies.

    Adapter-supplied. MCP wraps fastmcp.Context; CLI wraps stderr printer.
    Tool authors depend on the Protocol; implementation injected at invocation.
    """
    def info(self, msg: str, **fields: Any) -> None: ...
    def warning(self, msg: str, **fields: Any) -> None: ...
    def error(self, msg: str, **fields: Any) -> None: ...
    def debug(self, msg: str, **fields: Any) -> None: ...
    async def report_progress(self, current: int | float, total: int | float | None = None) -> None: ...
```

**Tool author pattern:**

```python
async def bulk_import(*, ctx: ToolContext, conn: Conn = Depends(get_conn), file: str) -> dict:
    ctx.info("starting import", file=file)
    items = await load(file)
    for i, item in enumerate(items):
        await ctx.report_progress(i, len(items))
        # process
    ctx.info("done", count=len(items))
    return {"imported": len(items)}
```

The `ctx` parameter is treated like a DI dependency — stripped from the input schema (via `signature.py`'s scanner detecting the Protocol type), supplied at invocation by the adapter.

**MCP adapter** (`packages/mcp/_context.py`, ~30 LOC): wraps `fastmcp.Context`. `ctx.info(msg, **fields)` → `fastmcp_ctx.info(...)`. `ctx.report_progress(...)` → `fastmcp_ctx.report_progress(...)`. Logs go over the MCP wire as protocol notifications.

**CLI adapter** (`packages/cli/_context.py`, ~40 LOC): prints to stderr in compact key=val text format:

```
[INFO] starting import file=path/to/data.csv
[INFO] progress 50/100
[WARN] retry attempt=2 reason="rate limited"
[ERROR] connection refused host=jira.example.com
```

LLM-friendly. No JSON noise. Tokens stay tight.

**Adapter binding:** `signature.py` scans the tool fn for a kwonly param annotated with `ToolContext`. At adapter time, the param is supplied by the adapter's implementation. Both adapters detect this via `_a2kit.context_param_name: str | None` field in `A2KitMeta`.

### Logging vs structlog

a2kit's CLI Context uses **plain stdlib + manual format**, not structlog. Reasons:

1. structlog adds a 200ms+ import cost (verified earlier as part of `logging.py` rabbit hole — `todo.md:96`).
2. CLI logs need compact text-for-LLM by default; structlog's default is JSON (good for production observability, wasteful for LLM CLI consumers).
3. Users who want structured logging in production MCP mode configure structlog themselves — FastMCP has its own logging middleware and the `Context.log()` API delivers structured fields over the wire.

**No `a2kit.logging` module.** Tool authors use `ctx.info(...)` (adapter-supplied) or import structlog directly if they want production-grade structured logging in their server module.

### Updated `A2KitMeta`

```python
@dataclass(frozen=True, slots=True)
class A2KitMeta:
    tool_name: str
    verb: Literal["read", "write", "list", "tool"]
    tags: frozenset[str]
    annotations: ToolAnnotations
    router_slug: str | None
    list_view: ListViewSettings | None
    enricher: EnricherFn | None
    context_param_name: str | None   # ← NEW: name of `ctx: ToolContext` param if present
```

### Net effect

- New core file: `a2kit/runtime.py` (~30 LOC, just the `ToolContext` Protocol).
- `packages/mcp/_context.py` (~30 LOC).
- `packages/cli/_context.py` (~40 LOC).
- `signature.py` gains a context-param scanner (~15 LOC).
- `A2KitMeta` gains one optional field.

Total addition: ~115 LOC for protocol-neutral logging + progress that works identically for MCP wire delivery and CLI stderr text. No structlog dependency.

## Audit Findings — Round 12 (FastMCP plugins + test structure; landed 2026-05-09)

### D-FastMCP-Plugin-Passthrough: `build_mcp_server` forwards kwargs to FastMCP ✅ NEW

FastMCP 3.x ships rich plugin surfaces on `FastMCP.__init__`: `auth`, `providers`, `transforms`, `lifespan`, `tools` (eager-register list), `tasks`, `session_state_store`, `sampling_handler`, etc. Built-in auth providers cover Google / Azure / OCI / etc.

**Decision:** `packages/mcp/build_mcp_server(app, **fastmcp_kwargs) -> FastMCP` forwards all extra kwargs to `FastMCP.__init__`. **a2kit does NOT ship an auth abstraction.** Auth is a wire-protocol concern; FastMCP owns it.

```python
# packages/mcp/server.py
def build_mcp_server(app: App, **fastmcp_kwargs) -> FastMCP:
    server = FastMCP(name=app.name, **fastmcp_kwargs)
    # ... register tools, middlewares, etc.
    return server
```

**User authoring with OAuth:**

```python
from fastmcp.server.auth.providers.google import GoogleAuthProvider
from a2kit.packages.mcp import build_mcp_server

server = build_mcp_server(
    app,
    auth=GoogleAuthProvider(client_id=..., client_secret=...),
)
```

**CLI mode** does not need auth (local invocation). `tracker tasks list-tasks` runs in-process; auth is meaningless. If a tool needs OAuth tokens, they're stored as connection secrets (Contract B's pydantic-settings cloud-secret backends handle this).

**Risk-radius:** zero. `**fastmcp_kwargs` is a passive forwarder; FastMCP plugin evolution doesn't require a2kit changes.

### D-Test-Structure: tests mirror application structure ✅ NEW

User direction: `tests/` should mirror `src/a2kit/` for navigation parity.

Current state: flat `tests/test_*.py` (24 files). Post-refactor:

```
tests/
├── conftest.py
├── test_app.py
├── test_tool.py
├── test_signature.py
├── test_routers.py
├── test_capabilities.py
├── test_runtime.py
├── test_meta.py
├── test_main.py
└── packages/
    ├── mcp/{test_server.py, test_context.py, middlewares/test_*.py}
    ├── cli/{test_builder.py, test_runtime.py, test_schemas.py, test_context.py}
    ├── connections/{test_store.py, test_config.py, ..., test_cli.py}
    ├── select/test_select.py
    ├── formatter/{test_response.py, test_toon.py, test_format_response.py}
    ├── enrichers/test_enrichers.py
    ├── testing/{test_snapshots.py, test_fixtures.py}
    └── lint/{test_static.py, test_runtime.py, test_di_rules.py}
```

**Migration approach:** during Phase 5 (tests migration), each subagent that builds a `packages/<name>/` adapter ALSO writes the corresponding `tests/packages/<name>/` tree. Existing tests get split / merged / renamed to fit. Coverage target ≥ 95% (100% nice-to-have).

This structure makes `pytest tests/packages/connections/` a natural slice for working on one package in isolation — a productivity improvement.

## Locked. The design is fully validated at every level audited.

12 rounds of audits complete. 25 numbered design decisions. All hypotheses tested or paper-analyzed. The architectural reinforcements are:

- **`A2KitMeta` typed-thin-waist contract** — converts every adapter's implicit string-key dependency into a compile-time-checkable typed contract.
- **Protocol-neutral enrichers + formatter** — error transformation and output formatting work identically for MCP and CLI; one place to optimize.
- **TOON default for LLM surfaces** — output, schemas, snapshots all flow through the same encoder.

The biggest external risk is `uncalled_for` (pre-1.0, every user tool fn depends on it). Mitigated by tight pinning and migration documentation. Every other dependency has a narrow blast radius confined to a single package.

## TL;DR for the handover session

**What this change does:** v1.0 break of a2kit. Reduces ~7.9K LOC → ~2.7K LOC. Splits into protocol-agnostic core (~1K LOC) + 7 plugin packages (~1.7K LOC). Single-entry `a2kit.run(app)` dispatches CLI tool calls, connection management, schema introspection, and MCP serve from one console script; only `serve` loads fastmcp.

**Final tree (post-implementation):**

```
src/a2kit/
├── __init__.py            ← PEP 562 lazy attrs + TYPE_CHECKING imports
├── __main__.py            ← `a2kit` console script (lint + connections subgroups)
├── _meta.py               ← A2KitMeta frozen dataclass (typed thin-waist contract)
├── runtime.py             ← ToolContext Protocol (logging + progress)
├── app.py                 ← App registry (~50 LOC)
├── tool.py                ← @tool/@read/@write/@list decorators; stamps A2KitMeta
├── signature.py           ← Annotated parsing + ctx scanner (no DI logic — uncalled_for owns it)
├── routers.py             ← Router, RouterRegistry
├── capabilities.py        ← Cap StrEnum + helpers
└── packages/
    ├── __init__.py
    ├── mcp/               ← FastMCP adapter; ONLY place fastmcp imports
    │   ├── server.py      ← build_mcp_server(app)
    │   ├── _context.py    ← ToolContext impl wrapping fastmcp.Context
    │   ├── middlewares/   ← listview.py, guards.py (subclass fastmcp Middleware)
    │   └── cli.py         ← serve_command (lazy-imported by build_full_cli)
    ├── cli/               ← Click adapter; build_full_cli; schema cmd
    │   ├── builder.py     ← build_full_cli(app) — LazyGroup + ContextVar
    │   ├── _context.py    ← ToolContext impl printing to stderr
    │   ├── schemas.py     ← compute_schema(fn) helper (also used by testing)
    │   └── runtime.py     ← in-process tool invocation flow
    ├── connections/       ← Contract B; pydantic-settings; _raw shadow for round-trip
    │   ├── store.py       ← ConnectionStore save/load/delete
    │   ├── config.py      ← ConnectionConfig(BaseSettings) + Key NamedTuple machinery
    │   ├── factory.py     ← get_conn_factory(app, ConnT)
    │   ├── filters.py     ← scope_filter + ephemeral/filtered store wrappers
    │   ├── tokens.py      ← op:// resolver (env via pydantic-settings native)
    │   └── cli.py         ← login/logout/list/show/delete Click subgroup
    ├── select/            ← cel-python compile + atom validation
    │   └── __init__.py    ← compile, evaluate, validate_atoms
    ├── formatter/         ← real TOON via toon-format; format_response orchestrator
    │   ├── response.py    ← Response, Page, Local, Passthrough types
    │   ├── toon.py        ← real TOON encoder (delegates to toon-format)
    │   └── __init__.py    ← format_response orchestrator + truncate
    ├── enrichers/         ← protocol-neutral wrap(fn, enricher)
    ├── testing/           ← syrupy SingleFileSnapshotExtension subclass
    │   ├── snapshots.py   ← per-tool TOON snapshots (reuses cli.schemas.compute_schema)
    │   └── fixtures.py    ← thin pytest fixtures + vcrpy glue
    └── lint/              ← static + runtime + cli (flattened from 11 files)
        ├── static.py      ← AST rules incl. A2K-DI-* family
        ├── runtime.py     ← runtime checks
        └── cli.py         ← Click entry
```

**Key locked decisions (top 10):**

1. **Take FastMCP as a hard dependency** — but isolate to `packages/mcp/`. Core stays fastmcp-free.
2. **uncalled_for canonical DI** — parameter-default form `*, conn: T = Depends(fn)`. Drop a2kit's `di.py` (177 LOC).
3. **Contract B for connections** — pydantic-settings native; eager `${VAR}` / `op://` resolution; cloud-secret backends free. `_raw: PrivateAttr` shadow preserves placeholders on round-trip.
4. **Real TOON via `toon-format`** — pin `==0.9.0b1` exact (PyPI 0.1.0 is a stub). a2kit's hand-rolled "toon" was actually TSV-with-JSON-cells; switch to standard.
5. **Single-entry `a2kit.run(app)`** — Click LazyGroup + ContextVar. Only `serve` loads fastmcp; everything else stays sub-second.
6. **Progressive CLI disclosure** — Click nested groups by Router (per-Router subgroups, per-tool subcommands).
7. **Protocol-neutral enrichers + formatter** — both work for MCP AND CLI invocations.
8. **TOON for schemas** — schema introspection output flows through the formatter (default TOON).
9. **`A2KitMeta` typed thin-waist** — frozen dataclass replaces untyped `_a2kit` dict; compile-time-safe contract.
10. **No re-exports of external symbols** — users import `from uncalled_for import Depends` directly. a2kit ships only what a2kit owns.

**Implementation phasing for `/opsx:apply`:**

1. **Sequential** (foundation): `_meta.py` → `tool.py` → `signature.py` → `app.py` → `routers.py` → `capabilities.py` → `exceptions.py`.
2. **Parallel via subagents** (one per package): `packages/connections/`, `packages/select/`, `packages/formatter/`, `packages/enrichers/`, `packages/testing/`, `packages/lint/`. Each is independent.
3. **Sequential after Phase 2**: `packages/mcp/` (depends on all of the above), `packages/cli/` (depends on all + `mcp` for the lazy `serve` registration).
4. **Sequential** (finishing): `__init__.py` lazy attrs, `__main__.py`, `pyproject.toml` deps + scripts, README rewrite, CHANGELOG, examples migration, test migration.

**Recommended subagent dispatch (Phase 2):** spawn 6 general-purpose agents in parallel, one per package, each with the package's spec section + the relevant Round-X audit findings as context.

**Open at implementation time:** none design-blocking. The 3 gotchas (round-trip secret leak, toon-format `--pre`, validate_call sentinel) are documented with mitigations in Round 8.

Implementation can begin.
