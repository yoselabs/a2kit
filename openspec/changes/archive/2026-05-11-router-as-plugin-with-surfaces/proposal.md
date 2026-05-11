## Why

Two unresolved smells from the a2web feedback rounds:

1. **`add_cli(connections_cli(X))` hides a multi-subsystem install.** One call
   registers a CLI group, an MCP tool surface, AND a DI provider — only
   visible in an adjacent `# this also installs …` comment. The chain
   signature lies about its blast radius.

2. **No way to express transport affinity per tool.** Credential management
   tools (`login`, `logout`) currently surface on every transport an `App`
   exposes. Agents have no business calling `login`. The plugin author knows
   this; today they have no way to say it.

These look like two problems but resolve to one architectural observation:
**`Router` and "plugin" are the same concept**. A router today is just
"a slug + a collection of decorated tools." A plugin (as `connections_cli`
demonstrates) is "a router with extras — providers, lifecycle hooks." Splitting
them into two types or two install verbs (`add_router` vs. a future `install`)
duplicates the unit of "stuff to register with an App."

This change collapses the duplication. `Router` becomes the canonical unit
of installation — tools, providers, lifecycle hooks, and per-tool surface
declarations all live on it. `app.add_router(r)` installs everything `r`
declares.

## What Changes

### Router grows three optional surface attributes

```python
class Router:
    providers:    tuple[type | Provider, ...] = ()
    # on_startup / on_shutdown hooks: methods named `on_startup`/`on_shutdown`
    # are discovered by the App during install (same pattern as tool collection)
```

`app.add_router(r)` installs:
- All decorated tools on `r` (existing behavior)
- All providers in `r.providers` (new — equivalent to `app.provide(*r.providers)`)
- `r.on_startup` / `r.on_shutdown` if defined (new — equivalent to
  `app.on_startup(r.on_startup)` / `app.on_shutdown(r.on_shutdown)`)

### `Surface` flag + `surfaces=` decorator kwarg

```python
from a2kit import Surface

class Surface(Flag):
    CLI = auto()
    MCP = auto()
    ALL = CLI | MCP

@read(surfaces=Surface.CLI)        # CLI subcommand only; no MCP tool
async def login(self, *, profile: str, token: str): ...

@read(surfaces=Surface.MCP)        # MCP tool only; no CLI command
async def search_internal(self, *, q: str): ...

@read()                            # default: Surface.ALL
async def list_connections(self): ...
```

Transport mounters (CLI builder, MCP server) filter tools by `Surface`
membership. A tool with `Surface.CLI` is silently skipped by the MCP
mounter, and vice versa. `Flag` so future surfaces (`HTTP`, `SSE`)
compose: `surfaces=Surface.CLI | Surface.HTTP`.

### `connections_cli` → `connections` factory + deprecation shim

```python
# v0.25 (deprecated, kept one release)
app.add_cli(connections_cli(TrackerConn))  # DeprecationWarning

# v0.26 (canonical)
app.add_router(connections(TrackerConn))
```

`connections(conn_cls)` returns a parameterized `Router` whose:
- `login` / `logout` carry `surfaces=Surface.CLI`
- `list_connections` carries the default `Surface.ALL`
- `providers = (conn_cls,)` is exposed on the Router
- Lifecycle (connection pool warm/close) lives in `on_startup` / `on_shutdown`

One-line diff for callers. No hidden behavior. The Router type carries the
full contract.

### `A2K-SURFACE-EXPLICIT` lint rule

A new static rule flags credential-named tools that default to `Surface.ALL`:

```
A2K-SURFACE-EXPLICIT  src/.../auth.py:42:5
  Tool `login` defaults to Surface.ALL. Credential-named tools SHOULD
  declare `surfaces=Surface.CLI` explicitly. Override or suppress per the
  rule docs if MCP exposure is intended.
```

Heuristic dictionary: `login`, `logout`, `auth*`, `*_credential*`,
`set_token`, `rotate_key`. Conservative — false positives are easier
to suppress than the smell is to spot.

### Documentation updates

- `OPERATIONAL_CONTRACTS.md` Q2 — replace "use `anyio.fail_after`" hint with
  full prescribed patterns: single-budget, nested multi-stage, silent degrade
  with `move_on_after`, cleanup-on-timeout interaction with Q1.
- `README.md` — promote imperative composition as canonical; demote fluent
  chain to "shorthand" note.

## Impact

### Affected code
- `src/a2kit/routers.py` — `Router` grows `providers` attribute; install
  pathway in `App.add_router` extended.
- `src/a2kit/app.py` — `add_router` installs providers + lifecycle.
- `src/a2kit/tool.py` / `signature.py` — `@read` / `@write` / `@list_`
  decorators accept `surfaces=` kwarg, stored in `meta.extra`.
- `src/a2kit/packages/mcp/server.py` — MCP mounter filters by `Surface.MCP`.
- `src/a2kit/packages/cli/builder.py` — CLI builder filters by `Surface.CLI`.
- `src/a2kit/packages/connections/` — new `connections(conn_cls)` factory;
  old `connections_cli` becomes a deprecation shim.
- `src/a2kit/packages/lint/rules/surface.py` — new `A2K-SURFACE-EXPLICIT` rule.

### Breaking changes
- `connections_cli` signature unchanged but emits `DeprecationWarning`.
  Removed in v0.27.
- Tool authors who relied on every tool being on every transport see no
  change — `Surface.ALL` is the default.

### Migration for a2web
```diff
- app.add_cli(connections_cli(TrackerConn))
+ app.add_router(connections(TrackerConn))
```

One-line diff. The new shape installs tools (CLI + MCP per the surface
declarations inside `connections`), providers, and lifecycle hooks via one
honest verb.
