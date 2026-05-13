# Replace `surfaces=Surface.*` with `visibility` tier

## Why

The current `surfaces=Surface.CLI|MCP|ALL` `Flag` enum was built to
gate transport-side mounting per tool. The audit (explore session
2026-05-13) surfaced four problems:

1. **Default-off hazard for future transports.** `Surface.ALL =
   CLI | MCP` is frozen at decorator-time. When REST or GraphQL
   land, every existing tool keeps the old flag value and silently
   does NOT mount on the new transport. The default means
   "every transport I knew about when this decorator ran," not
   "everywhere."

2. **Two ways to scope by transport.** The connections plugin's
   credential commands (the canonical use case) sidestep the
   decorator entirely — they ship as raw Click commands via
   `app.add_cli(connections_cli(...))`. So the documented per-tool
   `surfaces=Surface.CLI` mechanism has zero real consumers; the
   actual demand is met by composition-level routing.

3. **Per-router default missing.** The real-world demand is
   "this whole router is CLI-only" (every credential command on
   `ConnectionsRouter`). Currently the author must set
   `surfaces=Surface.CLI` on each of 5 methods. There is no
   `Router.surfaces` class attribute.

4. **Wrong axis.** CLI vs MCP is a *transport* axis. The actual
   threat-model axis is *audience*: operators (humans on CLI)
   vs agents (programmatic consumers via MCP/REST/GraphQL).
   These are asymmetric — agents discover everything they can
   call; operators only see what `--help` shows them. The
   `Surface` flag enum models them symmetrically and loses that
   asymmetry.

## What changes

Introduce a three-tier `visibility` kwarg + matching Router class
attribute. Default tier matches today's `Surface.ALL` behaviour.
Drop `Surface` entirely.

```python
Visibility = Literal["hidden", "cli", "all"]
```

| tier      | CLI invokable | in `--help`  | MCP / API / GraphQL  | use case                           |
|-----------|:-:|:-:|:-:|---|
| `hidden`  | ✓ | ✗ | ✗ | dangerous ops, debug probes        |
| `cli`     | ✓ | ✓ | ✗ | operator workflows (login/logout)  |
| `all`     | ✓ | ✓ | ✓ | default — everywhere               |

- **ADD** `visibility: Visibility | None = None` kwarg to all four
  verb decorators (`@a2kit.read/write/list_/tool`). `None` means
  "inherit from router".
- **ADD** `Router.visibility: ClassVar[Visibility] = "all"` class
  attribute. Per-tool kwarg overrides this when set explicitly.
- **REMOVE** `Surface` flag class from
  `src/a2kit/surface.py`. **DELETE** the file. Remove the
  top-level export.
- **REMOVE** `surfaces=` kwarg from all four verb decorators.
- **REMOVE** `meta.extras.surfaces` field; **ADD**
  `meta.extras.visibility: Visibility = "all"`.
- **UPDATE** CLI builder (`src/a2kit/packages/cli/builder.py`):
  - `visibility == "hidden"` → register with Click's
    `hidden=True` (omits from `--help`).
  - `visibility in ("hidden", "cli", "all")` → all mount on CLI.
- **UPDATE** MCP server (`src/a2kit/packages/mcp/server.py`):
  - `visibility in ("hidden", "cli")` → skip registration.
  - `visibility == "all"` → register.
- **UPDATE** lint rule (`src/a2kit/packages/lint/rules/surface.py`):
  credential-named tools (`login`, `logout`, etc.) suggest
  `visibility="cli"`.
- **PRIVATIZE** `connections_cli` factory — fold into
  `install_connections(app, *conn_types)`. After this change,
  the plugin consumer writes **one** call:

  ```python
  install_connections(app, TrackerConn)   # dispatch + scope + CLI
  ```

  Drop `connections_cli` from `a2kit.packages.connections.__all__`.

## Non-goals

- A `visibility="mcp"` tier (MCP-only, hidden from CLI). The audit
  found zero demand and the threat model doesn't motivate it.
- A `visibility="api"` tier separating REST/GraphQL from MCP.
  Treated uniformly as "programmatic surface" until a real use case
  splits them.
- Renaming `add_cli` / `add_mcp_middleware` core verbs.
- Touching `tags=` or `Cap` (handled in
  `prune-dead-decorator-surface`).

## Migration

| before                                | after                                  |
|---------------------------------------|----------------------------------------|
| `surfaces=Surface.ALL`                | drop (default)                         |
| `surfaces=Surface.CLI`                | `visibility="cli"`                     |
| `surfaces=Surface.MCP`                | no replacement (was unused — confirmed) |
| `surfaces=Surface.CLI \| Surface.MCP` | drop (default)                         |
| `install_connections(app, T) + app.add_cli(connections_cli(T))` | `install_connections(app, T)` |

Zero in-repo example callers. Downstream blast radius: lint rule
matches in a2web (connections plugin instances) — mechanical
replace.

## Risk

M. Breaking change to a public kwarg + a top-level export
(`a2kit.Surface`) + a plugin entry point (`connections_cli`).
Telegraphed via the lint rule update; mechanical migration in
downstream repos.
